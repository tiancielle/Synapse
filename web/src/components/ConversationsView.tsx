"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconChat, IconSearch, IconTrash } from "@/components/Icons";
import { Card, Chip, Empty, PageHeader, Skeleton } from "@/components/ui";
import { useConversations, useRunner } from "@/lib/hooks";
import { formatWhen } from "@/lib/labels";
import { visibleText } from "@/lib/messages";
import { remove, renameConversation, setActive } from "@/lib/runner";
import type { Conversation } from "@/lib/types";

function matches(c: Conversation, q: string): boolean {
  if (!q) return true;
  const n = q.toLowerCase();
  if (c.title.toLowerCase().includes(n)) return true;
  return c.messages.some((m) => (m.role === "user" ? m.text : visibleText(m)).toLowerCase().includes(n));
}

function statusOf(c: Conversation, running: boolean): { label: string; tone?: "ok" | "warn" | "bad" | "info" } {
  if (running) return { label: "en cours", tone: "info" };
  if (c.pending) return { label: "confirmation en attente", tone: "warn" };
  const last = [...c.messages].reverse().find((m) => m.role === "agent");
  if (last?.role === "agent" && last.status === "error") return { label: "erreur", tone: "bad" };
  if (last?.role === "agent" && last.status === "stopped") return { label: "arrêtée" };
  return { label: "terminée", tone: "ok" };
}

export default function ConversationsView() {
  const router = useRouter();
  const conversations = useConversations();
  const { run } = useRunner();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const list = conversations ? [...conversations].filter((c) => matches(c, query.trim())).sort((a, b) => b.updatedAt - a.updatedAt) : null;

  function open(id: string) {
    setActive(id);
    router.push("/studio");
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Espace de travail"
        title="Conversations"
        lead="Historique enregistré dans ce navigateur (l'API ne conserve pas les conversations). Recherche dans les titres et les messages."
      />
      <Card>
        <label className="search">
          <IconSearch size={16} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher une conversation…" aria-label="Rechercher" />
        </label>
        {list === null ? (
          <Skeleton lines={4} />
        ) : list.length === 0 ? (
          <Empty icon={<IconChat />} title={query ? "Aucune conversation ne correspond" : "Aucune conversation"}>
            {query ? "Essayez un autre mot." : "Posez une première question depuis la vue d'ensemble ou le Studio."}
          </Empty>
        ) : (
          <ul className="conv-table">
            {list.map((c) => {
              const busy = run?.convId === c.id;
              const st = statusOf(c, busy);
              const questions = c.messages.filter((m) => m.role === "user").length;
              return (
                <li key={c.id} className="conv-row">
                  {editing?.id === c.id ? (
                    <form
                      className="conv-rename"
                      onSubmit={(e) => {
                        e.preventDefault();
                        renameConversation(c.id, editing.value);
                        setEditing(null);
                      }}
                    >
                      <input
                        autoFocus
                        value={editing.value}
                        maxLength={80}
                        aria-label="Nouveau titre"
                        onChange={(e) => setEditing({ id: c.id, value: e.target.value })}
                        onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                      />
                      <button type="submit" className="btn btn-primary btn-small">
                        Enregistrer
                      </button>
                      <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing(null)}>
                        Annuler
                      </button>
                    </form>
                  ) : (
                    <button type="button" className="conv-open" onClick={() => open(c.id)}>
                      <span className="conv-row-title">{c.title}</span>
                      <span className="conv-row-meta">
                        {formatWhen(c.updatedAt)} · {questions} question{questions > 1 ? "s" : ""}
                      </span>
                    </button>
                  )}
                  <Chip tone={st.tone}>{st.label}</Chip>
                  <div className="conv-actions">
                    <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing({ id: c.id, value: c.title })}>
                      Renommer
                    </button>
                    {confirmId === c.id ? (
                      <button
                        type="button"
                        className="btn btn-small btn-danger"
                        autoFocus
                        onBlur={() => setConfirmId(null)}
                        onClick={() => {
                          remove(c.id);
                          setConfirmId(null);
                        }}
                      >
                        Confirmer la suppression
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="icon-btn"
                        disabled={busy}
                        aria-label={`Supprimer « ${c.title} »`}
                        title={busy ? "Exécution en cours" : "Supprimer"}
                        onClick={() => setConfirmId(c.id)}
                      >
                        <IconTrash size={16} />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
