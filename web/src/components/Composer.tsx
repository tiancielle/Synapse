"use client";

import { useEffect, useRef, useState } from "react";

import { IconArrowUp, IconStop } from "@/components/Icons";

const MAX = 2000;

type Props = {
  running: boolean; // une exécution est en cours (envoi impossible, bouton Arrêter visible)
  locked: boolean; // une confirmation est affichée : saisie bloquée
  onSend: (text: string) => void;
  onStop: () => void;
};

export default function Composer({ running, locked, onSend, onStop }: Props) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  // le champ grandit avec le texte (jusqu'à 200 px)
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function submit() {
    const text = value.trim();
    if (!text || running || locked) return;
    onSend(text);
    setValue("");
    field.current?.focus();
  }

  const placeholder = locked
    ? "Réponds d'abord à la demande de confirmation ci-dessus"
    : running
      ? "L'agent travaille… tu peux préparer ta prochaine question"
      : "Écris ta demande à l'agent…";

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="composer-box" data-locked={locked}>
        <textarea
          ref={field}
          rows={1}
          value={value}
          maxLength={MAX}
          disabled={locked}
          placeholder={placeholder}
          aria-label="Ta demande à l'agent"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-bar">
          <span className="composer-hint">
            {value.length > MAX - 300 ? `${value.length} / ${MAX}` : "Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne"}
          </span>
          {running ? (
            <button type="button" className="send send-stop" onClick={onStop} aria-label="Arrêter l'exécution">
              <IconStop size={16} />
            </button>
          ) : (
            <button type="submit" className="send" disabled={locked || !value.trim()} aria-label="Envoyer">
              <IconArrowUp size={18} />
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
