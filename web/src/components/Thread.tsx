"use client";

import { memo, useEffect, useRef } from "react";

import ConfirmCard from "@/components/ConfirmCard";
import { LogoMark } from "@/components/Icons";
import Markdown from "@/components/Markdown";
import { ServerIcon } from "@/components/ui";
import { toolTrace } from "@/lib/insights";
import { visibleText } from "@/lib/messages";
import type { Prompt } from "@/lib/prompts";
import { APP_NAME, type AgentMessage, type Conversation, type ServerName, type UserMessage } from "@/lib/types";

export type Suggestion = Prompt & { server: ServerName };

type Props = {
  conversation: Conversation | null; // null = nouvelle conversation (écran d'accueil)
  running: boolean;
  suggestions: Suggestion[];
  onSuggest: (text: string) => void;
  onDecide: (approved: boolean) => void;
};

function Welcome({ suggestions, onSuggest, disabled }: { suggestions: Suggestion[]; onSuggest: (t: string) => void; disabled: boolean }) {
  return (
    <div className="welcome">
      <LogoMark size={44} />
      <h2>Que voulez-vous confier à l&apos;agent ?</h2>
      <p>
        {APP_NAME} agit sur vos outils à votre place, sous le contrôle d&apos;un pare&#8209;feu : les actions sensibles demandent
        toujours votre confirmation.
      </p>
      {suggestions.length > 0 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s.title} type="button" className="suggestion" disabled={disabled} onClick={() => onSuggest(s.text)}>
              <span className="suggestion-icon">
                <ServerIcon server={s.server} size={18} />
              </span>
              <span className="suggestion-title">{s.title}</span>
              <span className="suggestion-text">{s.text}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const UserView = memo(function UserView({ msg }: { msg: UserMessage }) {
  return (
    <div className="user-row">
      <div className="user-bubble">{msg.text}</div>
    </div>
  );
});

const TRACE_LABEL = { running: "en cours", executed: "exécuté", blocked: "bloqué", error: "en échec" } as const;

function ToolTrace({ msg }: { msg: AgentMessage }) {
  const items = toolTrace(msg.events);
  if (items.length === 0) return null;
  return (
    <ol className="trace" aria-label="Outils appelés">
      {items.map((it) => (
        <li key={it.id} className="trace-item" data-state={it.state}>
          <ServerIcon server={it.server} size={13} />
          <code>{it.tool}</code>
          <span className="trace-state">{TRACE_LABEL[it.state]}</span>
          {it.alert && (
            <span className="trace-alert" title="Le détecteur (motifs connus) a retiré une partie du résultat">
              contenu suspect retiré
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

const AgentView = memo(function AgentView({ msg }: { msg: AgentMessage }) {
  const text = visibleText(msg);
  const running = msg.status === "running";
  return (
    <article className="agent" aria-label="Réponse de l'agent">
      <div className="agent-head">
        <LogoMark size={22} />
        <span>{APP_NAME}</span>
        {msg.status === "waiting" && <span className="agent-state">en attente de votre décision</span>}
      </div>
      <ToolTrace msg={msg} />
      {running && !text && (
        <div className="thinking" role="status">
          <span className="dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          L&apos;agent travaille…
        </div>
      )}
      {text && (
        <div className="agent-body">
          <Markdown text={text} />
          {running && <span className="caret" aria-hidden="true" />}
        </div>
      )}
      {msg.status === "stopped" && (
        <p className="notice notice-muted">Exécution arrêtée. La réponse est peut-être incomplète.</p>
      )}
      {msg.error && (
        <p className="notice notice-error" role="alert">
          {msg.error}
        </p>
      )}
      {msg.status === "done" && msg.verified === false && text && (
        <p className="notice notice-warn">
          Le vérificateur n&apos;a pas validé cette réponse. Vérifie-la avant de t&apos;y fier.
        </p>
      )}
    </article>
  );
});

function ThreadBody({ conversation, running, suggestions, onSuggest, onDecide }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true); // reste collé en bas tant que l'utilisateur n'a pas remonté

  function onScroll() {
    const el = scroller.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [conversation]);

  return (
    <div className="thread-scroll" ref={scroller} onScroll={onScroll}>
      <div className="thread" role="log" aria-live="polite" aria-busy={running} aria-label="Conversation">
        {!conversation || conversation.messages.length === 0 ? (
          <Welcome suggestions={suggestions} onSuggest={onSuggest} disabled={running} />
        ) : (
          conversation.messages.map((m) =>
            m.role === "user" ? <UserView key={m.id} msg={m} /> : <AgentView key={m.id} msg={m} />,
          )
        )}
        {conversation?.pending && <ConfirmCard request={conversation.pending} busy={running} onDecision={onDecide} />}
      </div>
    </div>
  );
}

export default function Thread(props: Props) {
  // la clé remet le défilement à zéro quand on change de conversation
  return <ThreadBody key={props.conversation?.id ?? "new"} {...props} />;
}
