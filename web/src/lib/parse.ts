// Validation des réponses JSON de l'API (health, audit). Module PUR, sans dépendance à l'exécution :
// testé avec `node --test` (les `import type` sont effacés par Node).
import type { AuditEntry, ConfirmationEvent, Decision, Health, ServerName, ToolOutcome } from "./types";

const SERVERS: ServerName[] = ["calendar", "mail", "github"];
const DECISIONS: Decision[] = ["auto", "notify", "confirm", "deny"];
const MAX_AUDIT = 2000; // borne d'affichage : le journal grossit pendant toute la vie de l'API

export const DEFAULT_API_URL = "http://127.0.0.1:8000";
const LOCAL_HOSTS = ["127.0.0.1", "localhost", "[::1]"];

/** Règle 4 : API locale uniquement. Une adresse non locale ou invalide est remplacée par l'adresse par défaut. */
export function localApiUrl(raw: string | undefined): string {
  if (!raw) return DEFAULT_API_URL;
  try {
    const u = new URL(raw);
    if ((u.protocol === "http:" || u.protocol === "https:") && LOCAL_HOSTS.includes(u.hostname)) return u.origin;
  } catch {
    // adresse illisible
  }
  return DEFAULT_API_URL;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function str(v: unknown, max = 200): string {
  return typeof v === "string" ? v.slice(0, max) : "";
}

/** Contrat v1.6. Champs absents (ancien backend) : valeurs prudentes ; `servers` absent = calendrier + mail (v1.4). */
export function toHealth(data: unknown): Health {
  const d = rec(data);
  const servers = Array.isArray(d.servers)
    ? SERVERS.filter((s) => (d.servers as unknown[]).includes(s))
    : (["calendar", "mail"] as ServerName[]);
  return {
    status: typeof d.status === "string" ? d.status : "ok",
    source: d.source === "google" ? "google" : "test",
    defenses: d.defenses === "toutes" || d.defenses === "aucune" || d.defenses === "registre" ? d.defenses : "inconnu",
    model: d.model === "demo" ? "demo" : "llm",
    llm: typeof d.llm === "string" && d.llm ? d.llm.slice(0, 80) : null,
    mail_source: d.mail_source === "gmail" ? "gmail" : "test",
    github_source: d.github_source === "github" ? "github" : "test",
    servers,
  };
}

/** Confirmation en attente relue depuis le navigateur : chaque champ est revalidé (une donnée modifiée à la main
 *  ne doit pas afficher autre chose qu'un texte borné). */
export function toPending(raw: unknown): ConfirmationEvent | null {
  const r = rec(raw);
  if (r.type !== "confirmation_required" || typeof r.tool !== "string" || !r.tool) return null;
  return { type: "confirmation_required", tool: r.tool.slice(0, 80), args: rec(r.args), reason: str(r.reason, 400), server: str(r.server, 40) || null };
}

export function toAuditEntry(raw: unknown): AuditEntry | null {
  const r = rec(raw);
  const decision = DECISIONS.find((x) => x === r.decision);
  if (typeof r.ts !== "number" || !decision || typeof r.tool !== "string") return null;
  const outcome: ToolOutcome = r.outcome === "executed" || r.outcome === "error" ? r.outcome : "blocked";
  return {
    ts: r.ts,
    server: str(r.server, 40) || "inconnu",
    tool: str(r.tool, 80),
    args: rec(r.args),
    decision,
    outcome,
    reason: str(r.reason, 300),
    findings: Array.isArray(r.findings) ? r.findings.filter((f): f is string => typeof f === "string").map((f) => f.slice(0, 60)) : [],
  };
}

export function toAuditEntries(data: unknown): AuditEntry[] {
  const entries = rec(data).entries;
  if (!Array.isArray(entries)) return [];
  return entries
    .slice(-MAX_AUDIT)
    .map(toAuditEntry)
    .filter((e): e is AuditEntry => e !== null);
}
