// Vue « intégrations » : catalogue (copie du registre) + état réel de l'API (health) + journal d'audit.
// Module PUR (seulement des `import type`) : testé avec `node --test`.
import type { AuditEntry, Decision, Health, ServerName } from "./types";

export type Risk = "read" | "soft_write" | "sensitive";

export type CatalogTool = { name: string; label: string; risk: Risk; scope: string; real: boolean };
export type CatalogServer = {
  label: string;
  description: string;
  sources: { test: string; real: string };
  realNote: string;
  tools: CatalogTool[];
};
export type Catalog = { servers: Record<ServerName, CatalogServer> };

export type ToolView = CatalogTool & {
  available: boolean; // exposé ET utilisable avec la source actuelle
  decision: Decision; // ce que le pare-feu décide avec le préréglage actuel
  calls: number;
};

export type ActivitySummary = { calls: number; executed: number; blocked: number; errors: number; alerts: number; last: number | null };

export type Integration = {
  name: ServerName;
  label: string;
  description: string;
  launched: boolean;
  real: boolean; // source réelle (Google, Gmail, GitHub) ou données de test
  sourceLabel: string;
  note: string | null;
  tools: ToolView[];
  activity: ActivitySummary;
};

export const SERVER_ORDER: ServerName[] = ["calendar", "mail", "github"];

const DECISION_BY_RISK: Record<Risk, Decision> = { read: "auto", soft_write: "notify", sensitive: "confirm" };

/** Décision du pare-feu (agent/firewall.py) : sans registre (« aucune »), tout passe en automatique. */
export function decisionFor(risk: Risk, defenses: Health["defenses"]): Decision {
  return defenses === "aucune" ? "auto" : DECISION_BY_RISK[risk];
}

export function isRealSource(server: ServerName, health: Health): boolean {
  if (server === "calendar") return health.source === "google";
  if (server === "mail") return health.mail_source === "gmail";
  return health.github_source === "github";
}

export function summarize(entries: AuditEntry[]): ActivitySummary {
  const s: ActivitySummary = { calls: 0, executed: 0, blocked: 0, errors: 0, alerts: 0, last: null };
  for (const e of entries) {
    s.calls += 1;
    if (e.outcome === "executed") s.executed += 1;
    else if (e.outcome === "error") s.errors += 1;
    else s.blocked += 1;
    if (e.findings.length > 0) s.alerts += 1;
    if (s.last === null || e.ts > s.last) s.last = e.ts;
  }
  return s;
}

export function buildIntegrations(catalog: Catalog, health: Health | null, audit: AuditEntry[]): Integration[] {
  return SERVER_ORDER.map((name) => {
    const c = catalog.servers[name];
    const launched = health ? health.servers.includes(name) : false;
    const real = health ? isRealSource(name, health) : false;
    const mine = audit.filter((e) => e.server === name);
    return {
      name,
      label: c.label,
      description: c.description,
      launched,
      real,
      sourceLabel: real ? c.sources.real : c.sources.test,
      note: real ? c.realNote : null,
      tools: c.tools.map((t) => ({
        ...t,
        available: launched && (!real || t.real),
        decision: decisionFor(t.risk, health?.defenses ?? "toutes"),
        calls: mine.filter((e) => e.tool === t.name).length,
      })),
      activity: summarize(mine),
    };
  });
}
