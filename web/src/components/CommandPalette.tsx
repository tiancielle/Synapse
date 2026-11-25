"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconArrowRight, IconSearch, IconSpark } from "@/components/Icons";
import { useRunner } from "@/lib/hooks";
import { NAV } from "@/lib/nav";
import { send } from "@/lib/runner";

type Action = { id: string; label: string; hint: string; run: () => void; ask?: boolean };

/** Palette (Ctrl+K) : poser une question à l'agent (nouvelle conversation) ou aller à une page. */
export default function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { run } = useRunner();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    input.current?.focus();
    return () => {
      if (opener.current instanceof HTMLElement) opener.current.focus(); // le focus revient où il était
    };
  }, []);

  const q = query.trim();
  const pages = NAV.filter((n) => !q || `${n.label} ${n.hint}`.toLowerCase().includes(q.toLowerCase()));
  const actions: Action[] = [
    ...(q
      ? [
          {
            id: "ask",
            ask: true,
            label: `Demander à l'agent : « ${q.length > 70 ? `${q.slice(0, 70)}…` : q} »`,
            hint: run ? "Une exécution est déjà en cours : attendez qu'elle se termine" : "Nouvelle conversation dans le Studio",
            run: () => {
              if (send(q, null)) router.push("/studio");
            },
          },
        ]
      : []),
    ...pages.map((n) => ({ id: n.key, label: n.label, hint: n.hint, run: () => router.push(n.href) })),
  ];
  const selected = Math.min(index, Math.max(0, actions.length - 1));

  function choose(a: Action | undefined) {
    if (!a || (a.ask && run)) return;
    a.run();
    onClose();
  }

  return (
    <div className="palette-scrim" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Palette de commandes"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            setIndex((selected + 1) % Math.max(1, actions.length));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setIndex((selected - 1 + actions.length) % Math.max(1, actions.length));
          } else if (e.key === "Enter" && !e.nativeEvent.isComposing) {
            e.preventDefault();
            choose(actions[selected]);
          } else if (e.key === "Tab") {
            e.preventDefault(); // le focus reste dans la palette
          }
        }}
      >
        <div className="palette-input">
          <IconSearch size={18} />
          <input
            ref={input}
            value={query}
            maxLength={2000}
            placeholder="Posez une question à l'agent, ou tapez le nom d'une page…"
            aria-label="Commande"
            aria-controls="palette-list"
            aria-activedescendant={actions[selected] ? `palette-${actions[selected].id}` : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
          />
          <kbd>Échap</kbd>
        </div>
        <ul className="palette-list" id="palette-list" role="listbox" aria-label="Résultats">
          {actions.map((a, i) => (
            <li
              key={a.id}
              id={`palette-${a.id}`}
              role="option"
              aria-selected={i === selected}
              aria-disabled={a.ask && run ? true : undefined}
              className="palette-item"
              data-ask={a.ask ? "true" : undefined}
              onMouseEnter={() => setIndex(i)}
              onClick={() => choose(a)}
            >
              <span className="palette-icon">{a.ask ? <IconSpark size={16} /> : <IconArrowRight size={16} />}</span>
              <span className="palette-text">
                <span className="palette-label">{a.label}</span>
                <span className="palette-hint">{a.hint}</span>
              </span>
            </li>
          ))}
          {actions.length === 0 && <li className="palette-empty">Aucune page ne correspond.</li>}
        </ul>
      </div>
    </div>
  );
}
