// Tests de la logique d'affichage (modules purs). Lancement : npm test (node --test, types effacés par Node).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { approvalHistory, filterAudit, pendingApprovals, runSteps, toolTrace, toolsUsed } from "../src/lib/insights.ts";
import { buildIntegrations, decisionFor, summarize, type Catalog } from "../src/lib/integrations.ts";
import { localApiUrl, toAuditEntries, toHealth, toPending } from "../src/lib/parse.ts";
import { suggestionsFor } from "../src/lib/prompts.ts";
import { readTheme } from "../src/lib/theme.ts";
import type { AgentEvent, AuditEntry, Conversation, Health } from "../src/lib/types.ts";

const catalog = JSON.parse(readFileSync(new URL("../src/lib/catalog.json", import.meta.url), "utf8")) as Catalog;

const HEALTH: Health = {
  status: "ok",
  source: "google",
  defenses: "toutes",
  model: "llm",
  llm: "ollama:test",
  mail_source: "gmail",
  github_source: "test",
  servers: ["calendar", "mail", "github"],
};

function entry(p: Partial<AuditEntry>): AuditEntry {
  return { ts: 100, server: "github", tool: "lister_depots", args: {}, decision: "auto", outcome: "executed", reason: "lecture", findings: [], ...p };
}

test("health v1.6 : champs lus, valeurs inconnues ramenées à des valeurs prudentes", () => {
  const h = toHealth({ status: "ok", source: "google", mail_source: "gmail", github_source: "github", servers: ["github", "pirate", "mail"], defenses: "x", model: "llm", llm: "m" });
  assert.deepEqual(h.servers, ["mail", "github"]); // ordre canonique, valeur inconnue ignorée
  assert.equal(h.defenses, "inconnu"); // jamais « Défenses complètes » par défaut
  assert.equal(toHealth({ defenses: "toutes" }).defenses, "toutes");
  assert.equal(h.github_source, "github");
  assert.deepEqual(toHealth({}).servers, ["calendar", "mail"]); // ancien backend (v1.4) : servers absent
  assert.equal(toHealth(null).mail_source, "test");
});

test("adresse de l'API : locale uniquement (règle 4)", () => {
  assert.equal(localApiUrl(undefined), "http://127.0.0.1:8000");
  assert.equal(localApiUrl("http://127.0.0.1:8001/"), "http://127.0.0.1:8001");
  assert.equal(localApiUrl("http://localhost:9000"), "http://localhost:9000");
  assert.equal(localApiUrl("https://exemple-attaque.test"), "http://127.0.0.1:8000");
  assert.equal(localApiUrl("http://127.0.0.1.exemple.test"), "http://127.0.0.1:8000");
  assert.equal(localApiUrl("javascript:alert(1)"), "http://127.0.0.1:8000");
});

test("confirmation relue du navigateur : champs revalidés et bornés", () => {
  assert.equal(toPending({ type: "autre", tool: "x" }), null);
  assert.equal(toPending({ type: "confirmation_required", tool: 3 }), null);
  const p = toPending({ type: "confirmation_required", tool: "envoyer_mail", args: "pas un objet", reason: "r".repeat(900), server: 5 });
  assert.deepEqual(p && { args: p.args, len: p.reason.length, server: p.server }, { args: {}, len: 400, server: null });
});

test("audit : entrées invalides ignorées, issue inconnue = bloquée", () => {
  const list = toAuditEntries({ entries: [{ ts: 1, tool: "t", decision: "auto", outcome: "??", server: "mail" }, { ts: "x" }, null, { ts: 2, tool: "u", decision: "nope" }] });
  assert.equal(list.length, 1);
  assert.equal(list[0].outcome, "blocked");
  assert.deepEqual(toAuditEntries({ entries: "pas une liste" }), []);
});

test("pare-feu affiché : registre appliqué, sauf préréglage « aucune »", () => {
  assert.equal(decisionFor("sensitive", "toutes"), "confirm");
  assert.equal(decisionFor("soft_write", "registre"), "notify");
  assert.equal(decisionFor("sensitive", "aucune"), "auto");
});

test("intégrations : seules les lectures sont disponibles avec une source réelle", () => {
  const [cal, mail, gh] = buildIntegrations(catalog, HEALTH, [entry({}), entry({ tool: "lister_depots", outcome: "error" })]);
  assert.equal(cal.real, true);
  assert.deepEqual(cal.tools.filter((t) => t.available).map((t) => t.name), ["lister_evenements", "chercher_evenements", "trouver_creneaux_libres"]);
  assert.deepEqual(mail.tools.filter((t) => t.available).map((t) => t.name), ["chercher_mails", "lire_mail"]);
  assert.equal(gh.real, false);
  assert.equal(gh.tools.every((t) => t.available), true);
  assert.equal(gh.tools.find((t) => t.name === "lister_depots")?.calls, 2);
  assert.equal(gh.activity.errors, 1);
});

test("intégrations : un serveur non lancé n'a aucun outil disponible ; API absente = rien de lancé", () => {
  const only = buildIntegrations(catalog, { ...HEALTH, servers: ["github"] }, []);
  assert.equal(only[0].launched, false);
  assert.equal(only[0].tools.some((t) => t.available), false);
  assert.equal(buildIntegrations(catalog, null, []).some((i) => i.launched), false);
});

test("résumé d'activité : compte par issue et alertes", () => {
  const s = summarize([entry({}), entry({ outcome: "blocked", ts: 300 }), entry({ outcome: "error", findings: ["exfiltration"] })]);
  assert.deepEqual(s, { calls: 3, executed: 1, blocked: 1, errors: 1, alerts: 1, last: 300 });
});

test("trace d'outils : chaque appel reçoit son issue, dans l'ordre, et l'alerte est rattachée", () => {
  const ev: AgentEvent[] = [
    { type: "tool_call", id: "a", name: "lire_issue", args: {}, server: "github" },
    { type: "tool_call", id: "b", name: "lire_issue", args: {}, server: "github" },
    { type: "firewall", tool: "lire_issue", decision: "auto", reason: "lecture", approved: true, server: "github" },
    { type: "tool_result", tool: "lire_issue", outcome: "executed", server: "github" },
    { type: "alert", tool: "lire_issue", findings: ["tool_hijack"], server: "github" },
    { type: "tool_result", tool: "lire_issue", outcome: "error", server: "github" },
    { type: "tool_call", id: "c", name: "envoyer_mail", args: {}, server: "mail" },
  ];
  const t = toolTrace(ev);
  assert.deepEqual(t.map((i) => i.state), ["executed", "error", "running"]);
  assert.equal(t[0].decision, "auto");
  assert.equal(t.some((i) => i.alert), true);
});

test("étapes : en attente de confirmation, puis terminé avec vérification refusée", () => {
  const waiting = runSteps({ status: "waiting", verified: null, events: [{ type: "plan", text: "p" }, { type: "tool_call", id: "x", name: "envoyer_mail", args: {}, server: "mail" }] });
  assert.equal(waiting[0].state, "done");
  assert.equal(waiting[3].detail, "En attente de votre décision");
  const done = runSteps({ status: "done", verified: false, events: [{ type: "verify", ok: false }, { type: "final", text: "x" }] });
  assert.equal(done[2].state, "warn");
  assert.equal(done[3].state, "done");
});

function conv(p: Partial<Conversation>): Conversation {
  return { id: "c1", sessionId: "s1", title: "T", createdAt: 1, updatedAt: 1, messages: [], pending: null, ...p };
}

test("approbations : en attente depuis les conversations, historique depuis l'audit", () => {
  const pending = conv({ id: "c2", updatedAt: 5, pending: { type: "confirmation_required", tool: "envoyer_mail", args: {}, reason: "r", server: "mail" } });
  assert.deepEqual(pendingApprovals([conv({}), pending]).map((p) => p.convId), ["c2"]);
  assert.deepEqual(pendingApprovals(null), []);
  const h = approvalHistory([entry({ decision: "confirm", outcome: "blocked", ts: 1 }), entry({ decision: "confirm", outcome: "executed", ts: 2 }), entry({})]);
  assert.deepEqual(h.map((x) => x.verdict), ["approved", "refused"]);
});

test("outils utilisés dans une conversation", () => {
  const c = conv({
    messages: [
      {
        id: "m",
        role: "agent",
        at: 1,
        status: "done",
        text: "",
        verified: true,
        error: null,
        events: [
          { type: "tool_call", id: "1", name: "chercher_mails", args: {}, server: "mail" },
          { type: "tool_result", tool: "chercher_mails", outcome: "executed", server: "mail" },
          { type: "tool_result", tool: "lire_mail", outcome: "blocked", server: "mail" },
        ],
      },
    ],
  });
  const used = toolsUsed(c);
  assert.equal(used.find((u) => u.tool === "chercher_mails")?.executed, 1);
  assert.equal(used.find((u) => u.tool === "lire_mail")?.refused, 1);
});

test("filtre du journal : serveur, issue, alerte et texte ; plus récent d'abord", () => {
  const all = [entry({ ts: 1 }), entry({ ts: 2, server: "mail", tool: "lire_mail" }), entry({ ts: 3, findings: ["x"] })];
  assert.deepEqual(filterAudit(all, { server: "all", outcome: "all", query: "" }).map((e) => e.ts), [3, 2, 1]);
  assert.deepEqual(filterAudit(all, { server: "mail", outcome: "all", query: "" }).map((e) => e.ts), [2]);
  assert.deepEqual(filterAudit(all, { server: "all", outcome: "alert", query: "" }).map((e) => e.ts), [3]);
  assert.deepEqual(filterAudit(all, { server: "all", outcome: "all", query: "LIRE" }).map((e) => e.ts), [2]);
});

test("suggestions : uniquement pour les serveurs lancés, en alternance", () => {
  assert.deepEqual(suggestionsFor([], 3), []);
  const s = suggestionsFor(["mail", "github"], 3);
  assert.equal(s.length, 3);
  assert.ok(s[0].text.includes("mails") && s[1].text.toLowerCase().includes("dépôts"));
});

test("thème : seule une valeur connue est acceptée", () => {
  assert.equal(readTheme("dark"), "dark");
  assert.equal(readTheme("light"), "light");
  assert.equal(readTheme("<script>"), "system");
  assert.equal(readTheme(null), "system");
});
