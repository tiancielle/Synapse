// Exécution de l'agent, PARTAGÉE par toutes les pages : une réponse en cours continue quand on change de page,
// et la barre de commande peut lancer une question depuis n'importe où. Une seule exécution à la fois
// (le serveur n'en traite qu'une). Lu avec useSyncExternalStore.
import { ApiError, streamPost } from "./api";
import { failAgentMessage, newAgentMessage, reduceAgentMessage, resumeAgentMessage, stopAgentMessage } from "./messages";
import { addConversation, getSnapshot, newConversation, newId, removeConversation, updateConversation } from "./storage";
import type { AgentEvent, AgentMessage, Conversation } from "./types";

const TOKEN_BATCH_MS = 40;

export type Run = { convId: string; msgId: string };
export type RunnerState = { run: Run | null; activeId: string | null; lastError: string | null };

let state: RunnerState = { run: null, activeId: null, lastError: null };
const listeners = new Set<() => void>();
let abort: AbortController | null = null;
let onFailure: (() => void) | null = null; // ex. revérifier l'état de l'API

function set(next: Partial<RunnerState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export function subscribeRunner(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
export function getRunner(): RunnerState {
  return state;
}
const SERVER_STATE: RunnerState = { run: null, activeId: null, lastError: null };
export function getServerRunner(): RunnerState {
  return SERVER_STATE;
}

export function setOnFailure(fn: (() => void) | null) {
  onFailure = fn;
}

export function setActive(id: string | null) {
  set({ activeId: id, lastError: null });
}

function patchAgent(convId: string, msgId: string, fn: (m: AgentMessage) => AgentMessage, extra?: (c: Conversation) => Conversation) {
  updateConversation(convId, (c) => {
    const next = { ...c, updatedAt: Date.now(), messages: c.messages.map((m) => (m.id === msgId && m.role === "agent" ? fn(m) : m)) };
    return extra ? extra(next) : next;
  });
}

async function execute(convId: string, msgId: string, path: string, body: unknown) {
  const controller = new AbortController();
  abort = controller;
  set({ run: { convId, msgId } });

  const apply = (event: AgentEvent) =>
    patchAgent(
      convId,
      msgId,
      (m) => reduceAgentMessage(m, event),
      (c) => {
        if (event.type === "confirmation_required") return { ...c, pending: event };
        if (event.type === "done" && event.status !== "waiting_confirmation") return { ...c, pending: null };
        return c;
      },
    );

  // Regroupement des tokens (certains modèles envoient un caractère par token) : un rendu toutes les 40 ms au plus.
  let tokenBuffer = "";
  let tokenTimer: ReturnType<typeof setTimeout> | undefined;
  const flushTokens = () => {
    if (tokenTimer !== undefined) {
      clearTimeout(tokenTimer);
      tokenTimer = undefined;
    }
    if (!tokenBuffer) return;
    const text = tokenBuffer;
    tokenBuffer = "";
    apply({ type: "token", text });
  };
  const onEvent = (event: AgentEvent) => {
    if (event.type === "token") {
      tokenBuffer += event.text;
      if (tokenTimer === undefined) tokenTimer = setTimeout(flushTokens, TOKEN_BATCH_MS);
      return;
    }
    flushTokens(); // tout autre événement : d'abord le texte en attente, pour garder l'ordre
    apply(event);
  };

  try {
    await streamPost(path, body, onEvent, controller.signal);
  } catch (e) {
    flushTokens();
    if (controller.signal.aborted) {
      // Arrêt demandé : l'agent a pu être interrompu en plein milieu. Par prudence, nouvelle session côté serveur.
      patchAgent(convId, msgId, stopAgentMessage, (c) => ({ ...c, sessionId: newId(), pending: null }));
    } else {
      const message = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
      patchAgent(convId, msgId, (m) => failAgentMessage(m, message), (c) => ({ ...c, pending: null }));
      onFailure?.();
    }
  } finally {
    flushTokens();
    abort = null;
    set({ run: null });
  }
}

/**
 * Envoie une question. `convId` null = nouvelle conversation (devient la conversation active).
 * Renvoie l'identifiant de la conversation, ou null si l'envoi est impossible (exécution en cours, confirmation en attente).
 */
export function send(text: string, convId: string | null): string | null {
  const message = text.trim();
  if (!message || state.run) return null;
  const existing = convId ? (getSnapshot() ?? []).find((c) => c.id === convId) ?? null : null;
  if (existing?.pending) {
    set({ lastError: "Une confirmation est en attente dans cette conversation : réponds-y d'abord." });
    return null;
  }
  const now = Date.now();
  const userMsg = { id: newId(), role: "user" as const, text: message, at: now };
  const agentMsg = newAgentMessage(newId(), now);
  let conv: Conversation;
  if (existing) {
    conv = existing;
    updateConversation(existing.id, (c) => ({ ...c, updatedAt: now, messages: [...c.messages, userMsg, agentMsg] }));
  } else {
    conv = { ...newConversation(message), messages: [userMsg, agentMsg] };
    addConversation(conv);
  }
  set({ activeId: conv.id, lastError: null });
  void execute(conv.id, agentMsg.id, "/api/chat", { session_id: conv.sessionId, message });
  return conv.id;
}

/** Réponse humaine à une demande de confirmation (le serveur reprend l'exécution suspendue). */
export function decide(convId: string, approved: boolean): boolean {
  if (state.run) return false;
  const conv = (getSnapshot() ?? []).find((c) => c.id === convId);
  if (!conv?.pending) return false;
  const waiting = [...conv.messages].reverse().find((m): m is AgentMessage => m.role === "agent" && m.status === "waiting");
  if (!waiting) return false;
  patchAgent(conv.id, waiting.id, resumeAgentMessage, (c) => ({ ...c, pending: null }));
  void execute(conv.id, waiting.id, "/api/confirm", { session_id: conv.sessionId, approved });
  return true;
}

export function stop() {
  abort?.abort();
}

export function remove(id: string): boolean {
  if (state.run?.convId === id) return false;
  removeConversation(id);
  if (state.activeId === id) set({ activeId: null });
  return true;
}

export function renameConversation(id: string, title: string) {
  const t = title.replace(/\s+/g, " ").trim().slice(0, 80);
  if (t) updateConversation(id, (c) => ({ ...c, title: t }));
}

/** Supprime toutes les conversations du navigateur (sauf celle en cours d'exécution). */
export function clearAll(): number {
  const list = getSnapshot() ?? [];
  let n = 0;
  for (const c of list) if (remove(c.id)) n += 1;
  return n;
}
