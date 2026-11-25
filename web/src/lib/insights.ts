// Calculs d'affichage à partir des événements d'une exécution, des conversations et du journal d'audit.
// Module PUR (seulement des `import type`) : testé avec `node --test`.
import type { AgentEvent, AgentMessage, AuditEntry, ConfirmationEvent, Conversation, Decision } from "./types";

export type StepState = "todo" | "active" | "done" | "warn";
export type Step = { key: "plan" | "tools" | "verify" | "answer"; label: string; state: StepState; detail: string };

/** Étapes du graphe (plan → outils → vérification → réponse) déduites des événements reçus. */
export function runSteps(msg: Pick<AgentMessage, "status" | "events" | "verified">): Step[] {
  const ev = msg.events;
  const has = (t: AgentEvent["type"]) => ev.some((e) => e.type === t);
  const calls = ev.filter((e) => e.type === "tool_call").length;
  const results = ev.filter((e): e is Extract<AgentEvent, { type: "tool_result" }> => e.type === "tool_result");
  const refused = results.filter((r) => r.outcome !== "executed").length;
  const running = msg.status === "running";
  const finished = msg.status === "done";
  const verified = has("verify");

  const plan: StepState = has("plan") || calls > 0 || verified ? "done" : running ? "active" : "todo";
  let tools: StepState = "todo";
  if (calls > 0) tools = running && !verified && !has("final") ? "active" : refused > 0 ? "warn" : "done";
  else if (verified || has("final")) tools = "done";
  else if (msg.status === "waiting") tools = "active";
  const verify: StepState = msg.verified === false ? "warn" : verified ? "done" : running && calls > 0 && results.length >= calls ? "active" : "todo";
  const answer: StepState = finished ? "done" : msg.status === "error" || msg.status === "stopped" ? "warn" : has("final") ? "done" : "todo";

  return [
    { key: "plan", label: "Planification", state: plan, detail: has("plan") ? "Plan établi" : "" },
    {
      key: "tools",
      label: "Outils",
      state: tools,
      detail: calls === 0 ? (tools === "done" ? "Aucun outil nécessaire" : "") : `${calls} appel${calls > 1 ? "s" : ""}${refused ? ` · ${refused} refusé${refused > 1 ? "s" : ""} ou en échec` : ""}`,
    },
    { key: "verify", label: "Vérification", state: verify, detail: msg.verified === false ? "Réponse non validée" : verified ? "Réponse validée" : "" },
    {
      key: "answer",
      label: "Réponse",
      state: answer,
      detail: msg.status === "waiting" ? "En attente de votre décision" : msg.status === "stopped" ? "Arrêtée" : msg.status === "error" ? "Erreur" : "",
    },
  ];
}

export type TraceItem = {
  id: string;
  server: string;
  tool: string;
  state: "running" | "executed" | "blocked" | "error";
  decision: Decision | null;
  alert: boolean;
};

/** Appels d'outils d'une réponse, dans l'ordre, avec leur issue (appariement appel → résultat par outil, dans l'ordre). */
export function toolTrace(events: AgentEvent[]): TraceItem[] {
  const items: TraceItem[] = [];
  const open = new Map<string, TraceItem[]>(); // clé serveur/outil -> appels sans résultat
  const key = (server: string | null | undefined, tool: string) => `${server ?? "inconnu"}/${tool}`;
  const first = (server: string | null | undefined, tool: string, pop: boolean) => {
    const list = open.get(key(server, tool)) ?? open.get(key(null, tool)) ?? [];
    return pop ? list.shift() : list[0];
  };
  for (const e of events) {
    if (e.type === "tool_call") {
      const item: TraceItem = { id: e.id || `${items.length}`, server: e.server ?? "inconnu", tool: e.name, state: "running", decision: null, alert: false };
      items.push(item);
      const k = key(e.server, e.name);
      open.set(k, [...(open.get(k) ?? []), item]);
    } else if (e.type === "firewall") {
      const it = first(e.server, e.tool, false);
      if (it) it.decision = e.decision;
    } else if (e.type === "alert") {
      const it = first(e.server, e.tool, false);
      if (it) it.alert = true;
      else {
        const last = [...items].reverse().find((i) => i.tool === e.tool);
        if (last) last.alert = true;
      }
    } else if (e.type === "tool_result") {
      const it = first(e.server, e.tool, true);
      if (it) it.state = e.outcome;
    }
  }
  return items;
}

export type ToolUse = { server: string; tool: string; calls: number; executed: number; refused: number; errors: number; alerts: number };

/** Outils utilisés dans une conversation (d'après les événements conservés dans le navigateur). */
export function toolsUsed(conv: Conversation | null): ToolUse[] {
  const map = new Map<string, ToolUse>();
  const get = (server: string | null | undefined, tool: string) => {
    const key = `${server ?? "inconnu"}/${tool}`;
    let u = map.get(key);
    if (!u) {
      u = { server: server ?? "inconnu", tool, calls: 0, executed: 0, refused: 0, errors: 0, alerts: 0 };
      map.set(key, u);
    }
    return u;
  };
  for (const m of conv?.messages ?? []) {
    if (m.role !== "agent") continue;
    for (const e of m.events) {
      if (e.type === "tool_call") get(e.server, e.name).calls += 1;
      else if (e.type === "tool_result") {
        const u = get(e.server, e.tool);
        if (e.outcome === "executed") u.executed += 1;
        else if (e.outcome === "error") u.errors += 1;
        else u.refused += 1;
      } else if (e.type === "alert") get(e.server, e.tool).alerts += 1;
    }
  }
  return [...map.values()];
}

export type PendingApproval = { convId: string; title: string; request: ConfirmationEvent; at: number };

export function pendingApprovals(conversations: Conversation[] | null): PendingApproval[] {
  return (conversations ?? [])
    .filter((c) => c.pending)
    .map((c) => ({ convId: c.id, title: c.title, request: c.pending as ConfirmationEvent, at: c.updatedAt }))
    .sort((a, b) => b.at - a.at);
}

export type ApprovalRecord = AuditEntry & { verdict: "approved" | "refused" };

/** Historique des actions soumises à confirmation humaine (journal d'audit, le plus récent d'abord). */
export function approvalHistory(audit: AuditEntry[]): ApprovalRecord[] {
  return audit
    .filter((e) => e.decision === "confirm")
    .map((e) => ({ ...e, verdict: e.outcome === "blocked" ? ("refused" as const) : ("approved" as const) }))
    .sort((a, b) => b.ts - a.ts);
}

/** Filtre du journal d'activité. */
export function filterAudit(audit: AuditEntry[], f: { server: string; outcome: string; query: string }): AuditEntry[] {
  const q = f.query.trim().toLowerCase();
  return audit
    .filter((e) => f.server === "all" || e.server === f.server)
    .filter((e) => f.outcome === "all" || (f.outcome === "alert" ? e.findings.length > 0 : e.outcome === f.outcome))
    .filter((e) => !q || e.tool.toLowerCase().includes(q) || e.reason.toLowerCase().includes(q))
    .sort((a, b) => b.ts - a.ts);
}
