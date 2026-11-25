"use client";

import { useState } from "react";

import Composer from "@/components/Composer";
import Sidebar from "@/components/Sidebar";
import SidePanel from "@/components/SidePanel";
import Thread, { type Suggestion } from "@/components/Thread";
import { IconPanel, IconPlus } from "@/components/Icons";
import { useConversations, useRunner } from "@/lib/hooks";
import { PROMPTS } from "@/lib/prompts";
import { decide, remove, send, setActive, stop } from "@/lib/runner";
import { useHealth } from "@/lib/useHealth";

/** Studio de l'agent : conversations, fil de la conversation et panneau de contexte (exécution en direct). */
export default function Chat() {
  const conversations = useConversations();
  const { run, activeId, lastError } = useRunner();
  const { health } = useHealth();
  const [panelOpen, setPanelOpen] = useState(true);
  const [listOpen, setListOpen] = useState(false);

  const active = conversations?.find((c) => c.id === activeId) ?? null;
  const running = run !== null;

  const suggestions: Suggestion[] = (health?.servers ?? []).flatMap((s) => PROMPTS[s].slice(0, 2).map((p) => ({ ...p, server: s }))).slice(0, 6);

  return (
    <div className="studio" data-panel={panelOpen ? "open" : "closed"}>
      <Sidebar
        conversations={conversations}
        activeId={active?.id ?? null}
        runningId={run?.convId ?? null}
        open={listOpen}
        onNew={() => {
          setActive(null);
          setListOpen(false);
        }}
        onSelect={(id) => {
          setActive(id);
          setListOpen(false);
        }}
        onDelete={(id) => void remove(id)}
        onClose={() => setListOpen(false)}
      />

      <section className="studio-main" aria-label="Conversation avec l'agent">
        <div className="studio-bar">
          <button type="button" className="btn btn-ghost btn-small studio-list-btn" onClick={() => setListOpen(true)}>
            Conversations
          </button>
          <h1 className="studio-title">{active?.title ?? "Nouvelle conversation"}</h1>
          {active && (
            <button type="button" className="btn btn-ghost btn-small" onClick={() => setActive(null)}>
              <IconPlus size={15} /> Nouvelle
            </button>
          )}
          <button
            type="button"
            className="icon-btn panel-toggle"
            onClick={() => setPanelOpen((v) => !v)}
            aria-pressed={panelOpen}
            aria-label={panelOpen ? "Masquer le panneau de contexte" : "Afficher le panneau de contexte"}
            title="Contexte d'exécution"
          >
            <IconPanel />
          </button>
        </div>
        <Thread
          conversation={active}
          running={running}
          suggestions={suggestions}
          onSuggest={(t) => void send(t, active?.id ?? null)}
          onDecide={(approved) => active && void decide(active.id, approved)}
        />
        {lastError && (
          <p className="notice notice-warn studio-notice" role="alert">
            {lastError}
          </p>
        )}
        <Composer
          running={running}
          locked={Boolean(active?.pending)}
          onSend={(t) => void send(t, active?.id ?? null)}
          onStop={stop}
        />
      </section>

      {panelOpen && <SidePanel conversation={active} running={running && run?.convId === active?.id} />}
    </div>
  );
}
