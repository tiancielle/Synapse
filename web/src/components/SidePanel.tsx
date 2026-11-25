"use client";

import Link from "next/link";

import { IconShield } from "@/components/Icons";
import { Chip, ServerTag } from "@/components/ui";
import { runSteps, toolsUsed } from "@/lib/insights";
import { DEFENSES_DETAIL, DEFENSES_LABEL, SERVER_LABEL } from "@/lib/labels";
import { isRealSource } from "@/lib/integrations";
import type { AgentMessage, Conversation } from "@/lib/types";
import { useHealth } from "@/lib/useHealth";

const STATE_LABEL = { todo: "à venir", active: "en cours", done: "terminé", warn: "à vérifier" } as const;

/** Panneau de contexte du Studio : modèle, défenses, progression de la dernière réponse, outils utilisés. */
export default function SidePanel({ conversation, running }: { conversation: Conversation | null; running: boolean }) {
  const { health, down } = useHealth();
  const last = [...(conversation?.messages ?? [])].reverse().find((m): m is AgentMessage => m.role === "agent") ?? null;
  const steps = last ? runSteps(last) : null;
  const used = toolsUsed(conversation);

  return (
    <aside className="sidepanel" aria-label="Contexte d'exécution">
      <section className="panel-section">
        <h2>Agent</h2>
        {down ? (
          <p className="panel-empty">API injoignable : lancez « run_api.py ».</p>
        ) : !health ? (
          <p className="panel-empty">Connexion à l&apos;API…</p>
        ) : (
          <dl className="facts">
            <div>
              <dt>Modèle</dt>
              <dd>{health.model === "demo" ? "Démo (réponses simulées)" : (health.llm ?? "Modèle réel")}</dd>
            </div>
            <div>
              <dt>Défenses</dt>
              <dd title={DEFENSES_DETAIL[health.defenses]}>
                <IconShield size={13} /> {DEFENSES_LABEL[health.defenses]}
              </dd>
            </div>
            <div>
              <dt>Serveurs</dt>
              <dd className="facts-tags">
                {health.servers.map((s) => (
                  <span key={s} className="facts-tag">
                    <ServerTag server={s} />
                    <Chip tone={isRealSource(s, health) ? "accent" : undefined}>{isRealSource(s, health) ? "réel" : "test"}</Chip>
                  </span>
                ))}
              </dd>
            </div>
          </dl>
        )}
      </section>

      <section className="panel-section">
        <h2>Progression{running && <span className="panel-live">en direct</span>}</h2>
        {!steps ? (
          <p className="panel-empty">Les étapes de l&apos;agent apparaîtront ici pendant qu&apos;il travaille.</p>
        ) : (
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={s.key} className="step" data-state={s.state}>
                <span className="step-dot" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="step-text">
                  <span className="step-label">{s.label}</span>
                  <span className="step-detail">{s.detail || STATE_LABEL[s.state]}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel-section">
        <h2>Utilisés dans cette conversation</h2>
        {used.length === 0 ? (
          <p className="panel-empty">Aucun outil utilisé pour le moment.</p>
        ) : (
          <ul className="used">
            {used.map((u) => (
              <li key={`${u.server}/${u.tool}`} className="used-item">
                <span className="used-name">
                  <code>{u.tool}</code>
                  <span className="used-server">{SERVER_LABEL[u.server] ?? u.server}</span>
                </span>
                <span className="used-counts">
                  {u.executed > 0 && <Chip tone="ok">{u.executed} ok</Chip>}
                  {u.refused > 0 && <Chip tone="warn">{u.refused} bloqué{u.refused > 1 ? "s" : ""}</Chip>}
                  {u.errors > 0 && <Chip tone="bad">{u.errors} échec{u.errors > 1 ? "s" : ""}</Chip>}
                  {u.alerts > 0 && <Chip tone="bad">{u.alerts} alerte{u.alerts > 1 ? "s" : ""}</Chip>}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/activity" className="panel-link">
          Voir tout le journal d&apos;audit
        </Link>
      </section>
    </aside>
  );
}
