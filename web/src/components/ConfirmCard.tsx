"use client";

import { useEffect, useRef } from "react";

import { IconShield } from "@/components/Icons";
import { truncate } from "@/lib/text";
import type { ConfirmationEvent } from "@/lib/types";

type Props = {
  request: ConfirmationEvent;
  busy: boolean;
  onDecision: (approved: boolean) => void;
};

/** Carte affichée dans la conversation quand le pare-feu demande l'accord de l'utilisateur. */
export default function ConfirmCard({ request, busy, onDecision }: Props) {
  const refuse = useRef<HTMLButtonElement>(null);

  // Le focus va sur « Refuser » : un appui accidentel sur Entrée ne peut pas autoriser une action sensible.
  // (les boutons sont désactivés tant que le flux n'est pas terminé, d'où la dépendance à `busy`)
  useEffect(() => {
    if (!busy) refuse.current?.focus();
  }, [busy]);

  // args et reason viennent du modèle : affichés en texte brut, jamais interprétés.
  let args = "";
  try {
    args = JSON.stringify(request.args, null, 2);
  } catch {
    args = String(request.args);
  }

  return (
    <section className="confirm" role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-desc">
      <div className="confirm-head">
        <span className="confirm-icon">
          <IconShield size={20} />
        </span>
        <div>
          <h2 id="confirm-title">Confirmation requise</h2>
          <p id="confirm-desc">
            L&apos;agent souhaite exécuter l&apos;outil <code>{truncate(request.tool, 80)}</code>
          </p>
        </div>
      </div>
      <div className="confirm-label">Arguments</div>
      <pre className="confirm-args">{truncate(args, 1500)}</pre>
      {request.reason && <p className="confirm-reason">{truncate(request.reason, 400)}</p>}
      <div className="confirm-actions">
        <button ref={refuse} type="button" className="btn btn-secondary" disabled={busy} onClick={() => onDecision(false)}>
          Refuser
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onDecision(true)}>
          Autoriser
        </button>
      </div>
    </section>
  );
}
