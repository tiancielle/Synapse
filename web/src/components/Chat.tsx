"use client";

import { useRef, useState, useSyncExternalStore } from "react";

import Composer from "@/components/Composer";
import Sidebar from "@/components/Sidebar";
import SidePanel from "@/components/SidePanel";
import Thread from "@/components/Thread";
import TopBar from "@/components/TopBar";
import { ApiError, streamPost } from "@/lib/api";
import {
  failAgentMessage,
  newAgentMessage,
  reduceAgentMessage,
  resumeAgentMessage,
  stopAgentMessage,
} from "@/lib/messages";
import {
  addConversation,
  getServerSnapshot,
  getSnapshot,
  newConversation,
  newId,
  removeConversation,
  subscribe,
  updateConversation,
} from "@/lib/storage";
import { useHealth } from "@/lib/useHealth";
import type { AgentEvent, AgentMessage, Conversation } from "@/lib/types";

const TOKEN_BATCH_MS = 40;

type Run = { convId: string; msgId: string };

/** Applique une modification au message de l'agent d'une conversation. */
function patchAgent(convId: string, msgId: string, fn: (m: AgentMessage) => AgentMessage, extra?: (c: Conversation) => Conversation) {
  updateConversation(convId, (c) => {
    const next = { ...c, updatedAt: Date.now(), messages: c.messages.map((m) => (m.id === msgId && m.role === "agent" ? fn(m) : m)) };
    return extra ? extra(next) : next;
  });
}

export default function Chat() {
  // Conversations : null tant que le navigateur n'a pas été lu (jamais de lecture pendant le rendu serveur).
  const conversations = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [activeId, setActiveId] = useState<string | null>(null); // null = nouvelle conversation
  const [run, setRun] = useState<Run | null>(null); // exécution en cours (une seule à la fois : le serveur n'en gère qu'une)
  const [panelOpen, setPanelOpen] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const { health, down, refresh } = useHealth();

  const active = conversations?.find((c) => c.id === activeId) ?? null;
  const running = run !== null;

  // ───── Exécution d'un appel à l'API (chat ou confirm) ─────
  async function execute(convId: string, msgId: string, path: string, body: unknown) {
    const controller = new AbortController();
    abort.current = controller;
    setRun({ convId, msgId });

    const apply = (event: AgentEvent) => {
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
    };

    // Regroupement des tokens : certains modèles envoient un caractère par token. On les accumule et on met
    // l'écran à jour au plus toutes les 40 ms, au lieu d'un rendu complet par caractère.
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
      flushTokens(); // tout autre événement : on affiche d'abord le texte en attente, pour garder l'ordre
      apply(event);
    };

    try {
      await streamPost(path, body, onEvent, controller.signal);
    } catch (e) {
      flushTokens();
      if (controller.signal.aborted) {
        // Arrêt demandé : le serveur peut avoir interrompu l'agent en plein milieu. Par prudence, la conversation
        // repart sur une nouvelle session (l'agent n'a plus la mémoire des échanges précédents).
        patchAgent(convId, msgId, stopAgentMessage, (c) => ({ ...c, sessionId: newId(), pending: null }));
      } else {
        const message = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
        patchAgent(convId, msgId, (m) => failAgentMessage(m, message), (c) => ({ ...c, pending: null }));
        void refresh(); // l'API est peut-être éteinte : on met le badge à jour
      }
    } finally {
      flushTokens();
      abort.current = null;
      setRun(null);
    }
  }

  function send(text: string) {
    if (running || active?.pending) return;
    const now = Date.now();
    const userMsg = { id: newId(), role: "user" as const, text, at: now };
    const agentMsg = newAgentMessage(newId(), now);

    let conv: Conversation;
    if (active) {
      conv = active;
      updateConversation(active.id, (c) => ({ ...c, updatedAt: now, messages: [...c.messages, userMsg, agentMsg] }));
    } else {
      conv = { ...newConversation(text), messages: [userMsg, agentMsg] };
      addConversation(conv);
      setActiveId(conv.id);
    }
    void execute(conv.id, agentMsg.id, "/api/chat", { session_id: conv.sessionId, message: text });
  }

  function decide(approved: boolean) {
    if (running || !active?.pending) return;
    const waiting = [...active.messages].reverse().find((m): m is AgentMessage => m.role === "agent" && m.status === "waiting");
    if (!waiting) return;
    patchAgent(active.id, waiting.id, resumeAgentMessage, (c) => ({ ...c, pending: null }));
    void execute(active.id, waiting.id, "/api/confirm", { session_id: active.sessionId, approved });
  }

  function stop() {
    abort.current?.abort();
  }

  function remove(id: string) {
    if (run?.convId === id) return;
    removeConversation(id);
    if (activeId === id) setActiveId(null);
  }

  return (
    <div className="shell" data-panel={panelOpen ? "open" : "closed"}>
      <Sidebar
        conversations={conversations}
        activeId={active?.id ?? null}
        runningId={run?.convId ?? null}
        open={sidebarOpen}
        onNew={() => {
          setActiveId(null);
          setSidebarOpen(false);
        }}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
        }}
        onDelete={remove}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="main">
        <TopBar
          title={active?.title ?? "Nouvelle conversation"}
          health={health}
          down={down}
          panelOpen={panelOpen}
          onMenu={() => setSidebarOpen(true)}
          onTogglePanel={() => setPanelOpen((v) => !v)}
          onRetry={() => void refresh()}
        />
        <Thread conversation={active} running={running} onSuggest={send} onDecide={decide} />
        <Composer running={running} locked={Boolean(active?.pending)} onSend={send} onStop={stop} />
      </main>

      {panelOpen && <SidePanel />}
    </div>
  );
}