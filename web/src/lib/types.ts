// Types partagés : événements de l'API (contrat v1) et données stockées dans le navigateur.

export const APP_NAME = "AgentFlow";

// ───────── Événements envoyés par l'API ─────────
export type Decision = "auto" | "notify" | "confirm" | "deny";

export type AgentEvent =
  | { type: "plan"; text: string }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { type: "firewall"; tool: string; decision: Decision; reason: string; approved: boolean }
  | { type: "tool_result"; tool: string; outcome: "executed" | "blocked" }
  | { type: "alert"; tool: string; findings: string[] }
  | { type: "tool_error"; tool: string; message: string }
  | { type: "verify"; ok: boolean }
  | { type: "confirmation_required"; tool: string; args: Record<string, unknown>; reason: string }
  | { type: "token"; text: string }
  | { type: "final"; text: string }
  | { type: "error"; message: string }
  | { type: "done"; status: "completed" | "waiting_confirmation" | "error" };

export type ConfirmationEvent = Extract<AgentEvent, { type: "confirmation_required" }>;

export type Health = {
  status: string;
  source: "test" | "google";
  defenses: "toutes" | "aucune" | "registre";
  model: "demo" | "llm";
  llm: string | null; // nom du modèle : absent tant que le backend ne l'envoie pas
};

// ───────── Données stockées (localStorage) ─────────
export type UserMessage = { id: string; role: "user"; text: string; at: number };

export type AgentStatus = "running" | "waiting" | "done" | "error" | "stopped";

export type AgentMessage = {
  id: string;
  role: "agent";
  at: number;
  status: AgentStatus;
  text: string; // réponse en cours de streaming, remplacée par l'événement « final »
  events: AgentEvent[]; // journal des étapes (sans les « token »), utilisé à l'étape 2
  verified: boolean | null; // dernier résultat du vérificateur (null = pas encore connu)
  error: string | null;
};

export type ChatMessage = UserMessage | AgentMessage;

export type Conversation = {
  id: string;
  sessionId: string; // identifiant de session envoyé à l'API
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  pending: ConfirmationEvent | null; // confirmation en attente (survit au rechargement)
};
