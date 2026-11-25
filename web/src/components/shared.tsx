"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconArrowRight, IconSpark } from "@/components/Icons";
import { DecisionBadge, OutcomeBadge, ServerIcon, ServerTag } from "@/components/ui";
import { useRunner } from "@/lib/hooks";
import { argsPreview, formatWhen } from "@/lib/labels";
import type { Prompt } from "@/lib/prompts";
import { send } from "@/lib/runner";
import type { AuditEntry, ServerName } from "@/lib/types";

/** Envoie une question à l'agent (nouvelle conversation) puis ouvre le Studio. */
export function useAsk() {
  const router = useRouter();
  const { run } = useRunner();
  return {
    busy: run !== null,
    ask: (text: string) => {
      if (send(text, null)) router.push("/studio");
    },
  };
}

export function PromptList({ prompts, server }: { prompts: Prompt[]; server?: ServerName }) {
  const { ask, busy } = useAsk();
  return (
    <ul className="prompt-list">
      {prompts.map((p) => (
        <li key={p.title}>
          <button type="button" className="prompt" disabled={busy} onClick={() => ask(p.text)} title={busy ? "Une exécution est en cours" : p.text}>
            <span className="prompt-icon">{server ? <ServerIcon server={server} size={16} /> : <IconSpark size={16} />}</span>
            <span className="prompt-text">
              <span className="prompt-title">{p.title}</span>
              <span className="prompt-body">{p.text}</span>
            </span>
            <IconArrowRight size={15} />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Barre de commande : une question = une nouvelle conversation dans le Studio. */
export function CommandBar({ placeholder }: { placeholder: string }) {
  const { ask, busy } = useAsk();
  const [value, setValue] = useState("");
  return (
    <form
      className="commandbar"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim() || busy) return;
        ask(value);
        setValue("");
      }}
    >
      <IconSpark size={18} />
      <input value={value} maxLength={2000} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} aria-label="Question à l'agent" />
      <button type="submit" className="btn btn-primary btn-small" disabled={busy || !value.trim()}>
        {busy ? "Exécution en cours…" : "Demander"}
      </button>
    </form>
  );
}

/** Ligne du journal d'audit (jamais de résultat d'outil : seulement l'appel et la décision). */
export function AuditRow({ e, onOpen, selected }: { e: AuditEntry; onOpen?: () => void; selected?: boolean }) {
  const content = (
    <>
      <span className="audit-time">{formatWhen(e.ts * 1000)}</span>
      <ServerTag server={e.server} />
      <code className="audit-tool">{e.tool}</code>
      <span className="audit-args">{argsPreview(e.args)}</span>
      <span className="audit-badges">
        {e.findings.length > 0 && <span className="chip chip-bad">alerte</span>}
        <DecisionBadge decision={e.decision} />
        <OutcomeBadge outcome={e.outcome} />
      </span>
    </>
  );
  if (!onOpen) return <li className="audit-row">{content}</li>;
  return (
    <li>
      <button type="button" className="audit-row audit-row-btn" aria-pressed={selected} onClick={onOpen}>
        {content}
      </button>
    </li>
  );
}
