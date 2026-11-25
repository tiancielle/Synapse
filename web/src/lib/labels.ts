// Libellés français affichés par l'interface (une seule source pour toutes les pages).
import type { Decision, Health, ToolOutcome } from "./types";

export const SERVER_LABEL: Record<string, string> = { calendar: "Calendrier", mail: "Mail", github: "GitHub", inconnu: "Inconnu" };

export const DECISION_LABEL: Record<Decision, string> = {
  auto: "Automatique",
  notify: "Notifié",
  confirm: "Confirmation humaine",
  deny: "Refusé",
};

export const OUTCOME_LABEL: Record<ToolOutcome, string> = { executed: "Exécuté", blocked: "Bloqué", error: "En échec" };

export const DEFENSES_LABEL: Record<Health["defenses"], string> = {
  toutes: "Défenses complètes",
  registre: "Registre de risques seul",
  aucune: "Aucune défense",
  inconnu: "Défenses : état inconnu",
};

export const DEFENSES_DETAIL: Record<Health["defenses"], string> = {
  toutes: "Registre des risques, confirmation humaine, analyse des résultats (motifs connus) et consignes renforcées.",
  registre: "Registre des risques et confirmation humaine, sans analyse des résultats.",
  aucune: "Mode de comparaison pour l'évaluation : aucune politique n'est appliquée.",
  inconnu: "L'API n'a pas indiqué un préréglage reconnu : vérifiez l'option --defenses de run_api.py.",
};

export const RISK_LABEL = { read: "Lecture", soft_write: "Écriture réversible", sensitive: "Action sensible" } as const;

const timeFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** ts en millisecondes. Même jour : heure seule ; sinon jour + heure. */
export function formatWhen(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  return d.toDateString() === now.toDateString() ? timeFmt.format(d) : dayFmt.format(d);
}

export function formatAgo(ms: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 45) return "à l'instant";
  const m = Math.round(s / 60);
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.round(h / 24)} j`;
}

/** Arguments d'outil en texte court (viennent du modèle : affichés en texte brut, jamais interprétés). */
export function argsPreview(args: Record<string, unknown>, max = 90): string {
  let s = "";
  try {
    s = Object.entries(args)
      .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
      .join(" · ");
  } catch {
    s = "";
  }
  return s.length > max ? `${s.slice(0, max)}…` : s;
}
