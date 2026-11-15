import type { AgentMessage, ChatMessage, Conversation, ConfirmationEvent } from "./types";
import { truncate } from "./text";

/**
 * Stockage des conversations dans le navigateur (localStorage) + petit « store » lisible avec
 * useSyncExternalStore. Rien n'est lu pendant le rendu serveur (getServerSnapshot renvoie null).
 */
const KEY = "agentflow:v1:conversations";
const SESSION_RE = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_CONVERSATIONS = 50;

export function newId(): string {
  // à n'appeler que dans des gestionnaires d'événements, jamais pendant le rendu
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function newConversation(firstQuestion: string): Conversation {
  const now = Date.now();
  return {
    id: newId(),
    sessionId: newId(),
    title: truncate(firstQuestion.replace(/\s+/g, " ").trim(), 48) || "Nouvelle conversation",
    createdAt: now,
    updatedAt: now,
    messages: [],
    pending: null,
  };
}

// ───────── Lecture / écriture ─────────
function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/** Nettoie ce qui vient du navigateur : une donnée corrompue ne doit jamais faire planter l'application. */
function sanitizeMessage(raw: unknown): ChatMessage | null {
  if (!isObject(raw) || typeof raw.id !== "string" || typeof raw.text !== "string") return null;
  const at = typeof raw.at === "number" ? raw.at : Date.now();
  if (raw.role === "user") return { id: raw.id, role: "user", text: raw.text, at };
  if (raw.role === "agent") {
    const statuses = ["running", "waiting", "done", "error", "stopped"];
    let status = statuses.includes(String(raw.status)) ? (raw.status as AgentMessage["status"]) : "done";
    if (status === "running") status = "stopped"; // page rechargée en plein milieu d'une exécution
    return {
      id: raw.id,
      role: "agent",
      at,
      status,
      text: raw.text,
      events: Array.isArray(raw.events) ? (raw.events as AgentMessage["events"]) : [],
      verified: typeof raw.verified === "boolean" ? raw.verified : null,
      error: typeof raw.error === "string" ? raw.error : null,
    };
  }
  return null;
}

function sanitizeConversation(raw: unknown): Conversation | null {
  if (!isObject(raw) || typeof raw.id !== "string" || typeof raw.sessionId !== "string") return null;
  if (!SESSION_RE.test(raw.sessionId) || !Array.isArray(raw.messages)) return null;
  const messages = raw.messages.map(sanitizeMessage).filter((m): m is ChatMessage => m !== null);
  const pending = isObject(raw.pending) && raw.pending.type === "confirmation_required" ? (raw.pending as ConfirmationEvent) : null;
  const hasWaiting = messages.some((m) => m.role === "agent" && m.status === "waiting");
  return {
    id: raw.id,
    sessionId: raw.sessionId,
    title: typeof raw.title === "string" && raw.title ? raw.title : "Conversation",
    createdAt: typeof raw.createdAt === "number" ? raw.createdAt : Date.now(),
    updatedAt: typeof raw.updatedAt === "number" ? raw.updatedAt : Date.now(),
    messages,
    pending: hasWaiting ? pending : null,
  };
}

function read(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data.map(sanitizeConversation).filter((c): c is Conversation => c !== null);
  } catch {
    return []; // stockage indisponible (navigation privée…) ou JSON corrompu
  }
}

function write(list: Conversation[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // quota dépassé ou stockage bloqué : l'application continue en mémoire
  }
}

// ───────── Store ─────────
let state: Conversation[] | null = null; // null = pas encore chargé
const listeners = new Set<() => void>();
let saveTimer: ReturnType<typeof setTimeout> | undefined;

function flush() {
  if (saveTimer !== undefined) {
    clearTimeout(saveTimer);
    saveTimer = undefined;
  }
  if (state) write(state);
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
}

function commit(next: Conversation[]) {
  state = next.slice(0, MAX_CONVERSATIONS);
  if (saveTimer === undefined) saveTimer = setTimeout(flush, 400); // le streaming met à jour très souvent
  listeners.forEach((l) => l());
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSnapshot(): Conversation[] | null {
  if (state === null && typeof window !== "undefined") state = read();
  return state;
}

export function getServerSnapshot(): Conversation[] | null {
  return null;
}

// ───────── Actions ─────────
export function addConversation(conv: Conversation) {
  commit([conv, ...(getSnapshot() ?? [])]);
}

export function updateConversation(id: string, fn: (c: Conversation) => Conversation) {
  commit((getSnapshot() ?? []).map((c) => (c.id === id ? fn(c) : c)));
}

export function removeConversation(id: string) {
  commit((getSnapshot() ?? []).filter((c) => c.id !== id));
}
