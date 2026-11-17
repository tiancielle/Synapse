// Types partagés : événements de l'API (contrat v1.4) et données stockées dans le navigateur.

export const APP_NAME = "AgentFlow";

// ───────── Événements envoyés par l'API ─────────
export type Decision = "auto" | "notify" | "confirm" | "deny";

// « error » = l'outil a été autorisé puis a échoué ; « blocked » = refusé par le pare-feu ou par l'utilisateur
export type ToolOutcome = "executed" | "blocked" | "error";

// `server` = serveur MCP qui porte l'outil (« calendar », « mail »…). Optionnel : absent des anciens serveurs d'API.
export type AgentEvent =
  | { type: "plan"; text: string }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown>; server?: string | null }
  | { type: "firewall"; tool: string; decision: Decision; reason: string; approved: boolean; server?: string | null }
  | { type: "tool_result"; tool: string; outcome: ToolOutcome; server?: string | null }
  | { type: "alert"; tool: string; findings: string[]; server?: string | null }
  | { type: "tool_error"; tool: string; message: string; server?: string | null }
  | { type: "verify"; ok: boolean }
  | { type: "confirmation_required"; tool: string; args: Record<string, unknown>; reason: string; server?: string | null }
  | { type: "token"; text: string } // morceau de la réponse en cours (« final » reste la référence)
  | { type: "final"; text: string }
  | { type: "error"; message: string }
  | { type: "done"; status: "completed" | "waiting_confirmation" | "error" };

export type ConfirmationEvent = Extract<AgentEvent, { type: "confirmation_required" }>;

export type Health = {
  status: string;
  source: "test" | "google";
  defenses: "toutes" | "aucune" | "registre";
  model: "demo" | "llm";
  llm: string | null; // nom du modèle, affiché dans l'en-tête (null si le backend ne l'envoie pas)
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