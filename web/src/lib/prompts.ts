// Questions prêtes à envoyer à l'agent, par serveur MCP. Elles n'utilisent que des outils réellement exposés.
import type { ServerName } from "./types";

export type Prompt = { title: string; text: string };

export const PROMPTS: Record<ServerName, Prompt[]> = {
  calendar: [
    { title: "Préparer ma semaine", text: "Prépare ma semaine : liste mes rendez-vous et signale les conflits." },
    { title: "Prochains rendez-vous", text: "Quels sont mes prochains rendez-vous ?" },
    { title: "Créneau libre", text: "Trouve-moi un créneau libre d'une heure demain." },
  ],
  mail: [
    { title: "Mails non lus", text: "Résume mes mails non lus de cette semaine." },
    { title: "Chercher un mail", text: "Cherche les mails qui parlent de réunion ce mois-ci." },
  ],
  github: [
    { title: "Mes dépôts", text: "Quels sont mes dépôts GitHub ?" },
    { title: "Pull requests ouvertes", text: "Ai-je des pull requests ouvertes sur mes projets ?" },
    { title: "Ma semaine de code", text: "Qu'ai-je poussé cette semaine ?" },
    { title: "Trouver un projet", text: "Je cherche un projet public sur GitHub pour apprendre la data science." },
  ],
};

/** Suggestions pour les serveurs lancés (au plus `max`, en alternant les serveurs). */
export function suggestionsFor(servers: ServerName[], max = 3): Prompt[] {
  const lists = servers.map((s) => PROMPTS[s]);
  const out: Prompt[] = [];
  for (let i = 0; out.length < max && lists.some((l) => i < l.length); i += 1) {
    for (const l of lists) if (i < l.length && out.length < max) out.push(l[i]);
  }
  return out;
}
