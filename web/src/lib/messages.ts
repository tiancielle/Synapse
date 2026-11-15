import type { AgentEvent, AgentMessage } from "./types";
import { stripThinking } from "./text";

const MAX_EVENTS = 200;

export function newAgentMessage(id: string, at: number): AgentMessage {
  return { id, role: "agent", at, status: "running", text: "", events: [], verified: null, error: null };
}

/**
 * Fonction pure : applique un événement de l'API à un message de l'agent.
 * (Elle sera étendue à l'étape 2 pour la progression et le chronomètre, et se teste facilement.)
 */
export function reduceAgentMessage(msg: AgentMessage, event: AgentEvent): AgentMessage {
  switch (event.type) {
    case "token":
      return { ...msg, text: msg.text + event.text };
    case "final":
      // « final » est LA référence : il remplace le texte reçu en streaming
      return { ...msg, text: event.text, events: addEvent(msg.events, event) };
    case "tool_call":
      // le texte streamé avant un appel d'outil n'est pas la réponse finale : on repart de zéro
      return { ...msg, text: "", events: addEvent(msg.events, event) };
    case "verify":
      // réponse refusée : l'agent va réécrire, on efface le texte rejeté
      return { ...msg, verified: event.ok, text: event.ok ? msg.text : "", events: addEvent(msg.events, event) };
    case "error":
      return { ...msg, error: event.message, events: addEvent(msg.events, event) };
    case "confirmation_required":
      return { ...msg, status: "waiting", events: addEvent(msg.events, event) };
    case "done":
      if (event.status === "waiting_confirmation") return { ...msg, status: "waiting" };
      if (event.status === "error") return { ...msg, status: "error", error: msg.error ?? "L'agent a rencontré une erreur." };
      return { ...msg, status: "done" };
    default:
      return { ...msg, events: addEvent(msg.events, event) };
  }
}

function addEvent(events: AgentEvent[], event: AgentEvent): AgentEvent[] {
  const next = [...events, event];
  return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
}

/** Après une confirmation : le même message de l'agent reprend. */
export function resumeAgentMessage(msg: AgentMessage): AgentMessage {
  return { ...msg, status: "running", error: null };
}

export function failAgentMessage(msg: AgentMessage, error: string): AgentMessage {
  return { ...msg, status: "error", error };
}

export function stopAgentMessage(msg: AgentMessage): AgentMessage {
  return { ...msg, status: "stopped" };
}

/** Texte prêt à afficher (sans blocs de réflexion du modèle). */
export function visibleText(msg: AgentMessage): string {
  return stripThinking(msg.text);
}
