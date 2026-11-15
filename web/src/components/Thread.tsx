"use client";

import { memo, useEffect, useRef } from "react";

import ConfirmCard from "@/components/ConfirmCard";
import { IconCalendar, IconClock, IconSwap, LogoMark } from "@/components/Icons";
import Markdown from "@/components/Markdown";
import { visibleText } from "@/lib/messages";
import { APP_NAME, type AgentMessage, type Conversation, type UserMessage } from "@/lib/types";

const SUGGESTIONS = [
  { icon: <IconCalendar size={18} />, title: "Préparer ma semaine", text: "Prépare ma semaine" },
  { icon: <IconClock size={18} />, title: "Prochains rendez-vous", text: "Quels sont mes prochains rendez-vous ?" },
  { icon: <IconSwap size={18} />, title: "Conflits d'agenda", text: "Y a-t-il des conflits dans mon planning cette semaine ?" },
];

type Props = {
  conversation: Conversation | null; // null = nouvelle conversation (écran d'accueil)
  running: boolean;
  onSuggest: (text: string) => void;
  onDecide: (approved: boolean) => void;
};

function Welcome({ onSuggest, disabled }: { onSuggest: (t: string) => void; disabled: boolean }) {
  return (
    <div className="welcome">
      <LogoMark size={44} />
      <h2>Que puis-je faire pour votre agenda ?</h2>
      <p>
        {APP_NAME} agit sur vos outils à votre place, sous le contrôle d&apos;un pare&#8209;feu : les actions sensibles demandent
        toujours votre confirmation.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s.title} type="button" className="suggestion" disabled={disabled} onClick={() => onSuggest(s.text)}>
            <span className="suggestion-icon">{s.icon}</span>
            <span className="suggestion-title">{s.title}</span>
            <span className="suggestion-text">{s.text}</span>
          </button>
        ))}
      </div>
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

function ThreadBody({ conversation, running, onSuggest, onDecide }: Props) {
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
          <Welcome onSuggest={onSuggest} disabled={running} />
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
