import type { AgentEvent, Decision } from "./types";
import { toText } from "./text";

const DECISIONS: Decision[] = ["auto", "notify", "confirm", "deny"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

/** Valide un objet JSON reçu et le convertit en événement typé (null si inconnu ou invalide). */
export function toAgentEvent(raw: unknown): AgentEvent | null {
  if (!isRecord(raw) || typeof raw.type !== "string") return null;
  switch (raw.type) {
    case "plan":
      return { type: "plan", text: toText(raw.text) };
    case "tool_call":
      return { type: "tool_call", id: toText(raw.id), name: toText(raw.name), args: asRecord(raw.args) };
    case "firewall": {
      const decision = DECISIONS.find((d) => d === raw.decision);
      if (!decision) return null;
      return { type: "firewall", tool: toText(raw.tool), decision, reason: toText(raw.reason), approved: raw.approved === true };
    }
    case "tool_result":
      return { type: "tool_result", tool: toText(raw.tool), outcome: raw.outcome === "executed" ? "executed" : "blocked" };
    case "alert":
      return {
        type: "alert",
        tool: toText(raw.tool),
        findings: Array.isArray(raw.findings) ? raw.findings.map((f) => toText(f)) : [],
      };
    case "tool_error":
      return { type: "tool_error", tool: toText(raw.tool), message: toText(raw.message) };
    case "verify":
      return { type: "verify", ok: raw.ok === true };
    case "confirmation_required":
      return { type: "confirmation_required", tool: toText(raw.tool), args: asRecord(raw.args), reason: toText(raw.reason) };
    case "token":
      return { type: "token", text: toText(raw.text) };
    case "final":
      return { type: "final", text: toText(raw.text) };
    case "error":
      return { type: "error", message: toText(raw.message) };
    case "done": {
      const status = raw.status === "waiting_confirmation" || raw.status === "error" ? raw.status : "completed";
      return { type: "done", status };
    }
    default:
      return null; // type inconnu (évolution future de l'API) : ignoré
  }
}

/**
 * Découpe un flux SSE : renvoie les événements complets et le reste (message incomplet)
 * à réinjecter au prochain morceau reçu.
 */
export function parseSse(buffer: string): { events: AgentEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: AgentEvent[] = [];
  for (const block of blocks) {
    // Un message peut tenir sur plusieurs lignes « data: » : on les joint avant de lire le JSON.
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue;
    try {
      const event = toAgentEvent(JSON.parse(data));
      if (event) events.push(event);
    } catch {
      // JSON illisible : ignoré
    }
  }
  return { events, rest };
}
