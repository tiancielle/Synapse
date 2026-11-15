"use client";

import { useState } from "react";

import { IconPlus, IconTrash, LogoMark } from "@/components/Icons";
import { APP_NAME, type Conversation } from "@/lib/types";

type Props = {
  conversations: Conversation[] | null; // null = chargement depuis le navigateur
  activeId: string | null;
  runningId: string | null; // conversation dont l'exécution est en cours (non supprimable)
  open: boolean; // tiroir ouvert (petits écrans)
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
};

export default function Sidebar({ conversations, activeId, runningId, open, onNew, onSelect, onDelete, onClose }: Props) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const sorted = conversations ? [...conversations].sort((a, b) => b.updatedAt - a.updatedAt) : null;

  return (
    <>
      {open && <div className="scrim" onClick={onClose} aria-hidden="true" />}
      <aside className="sidebar" data-open={open} aria-label="Conversations">
        <div className="brand">
          <LogoMark size={30} />
          <span className="brand-name">{APP_NAME}</span>
        </div>

        <button type="button" className="btn btn-new" onClick={onNew}>
          <IconPlus size={16} /> Nouvelle conversation
        </button>

        <div className="side-label">Conversations</div>
        <nav className="conv-list">
          {sorted === null && (
            <div className="skeletons" aria-hidden="true">
              <span className="skeleton" />
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          )}
          {sorted?.length === 0 && <p className="side-empty">Aucune conversation pour le moment.</p>}
          <ul>
            {sorted?.map((c) => {
              const busy = c.id === runningId;
              const asking = confirmId === c.id;
              return (
                <li key={c.id} className="conv-item" data-active={c.id === activeId}>
                  <button
                    type="button"
                    className="conv"
                    aria-current={c.id === activeId ? "page" : undefined}
                    onClick={() => {
                      setConfirmId(null);
                      onSelect(c.id);
                    }}
                  >
                    <span className="conv-title">{c.title}</span>
                    {busy && <span className="conv-dot" title="Exécution en cours" />}
                  </button>
                  {asking ? (
                    <button
                      type="button"
                      className="conv-delete conv-delete-confirm"
                      onClick={() => {
                        setConfirmId(null);
                        onDelete(c.id);
                      }}
                      onBlur={() => setConfirmId(null)}
                      autoFocus
                    >
                      Supprimer ?
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="conv-delete"
                      disabled={busy}
                      aria-label={`Supprimer la conversation « ${c.title} »`}
                      title={busy ? "Exécution en cours" : "Supprimer"}
                      onClick={() => setConfirmId(c.id)}
                    >
                      <IconTrash size={15} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </nav>

        <p className="side-foot">Conversations enregistrées uniquement dans ce navigateur.</p>
      </aside>
    </>
  );
}
