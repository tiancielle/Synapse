"use client";

import { useState } from "react";

import { IconPulse, IconRefresh } from "@/components/Icons";
import { AuditRow } from "@/components/shared";
import { Card, DecisionBadge, Empty, OutcomeBadge, PageHeader, ServerTag, Skeleton, Stat } from "@/components/ui";
import { useAudit } from "@/lib/hooks";
import { filterAudit } from "@/lib/insights";
import { summarize } from "@/lib/integrations";
import { formatWhen, SERVER_LABEL } from "@/lib/labels";
import type { AuditEntry } from "@/lib/types";

const OUTCOMES = [
  { value: "all", label: "Toutes les issues" },
  { value: "executed", label: "Exécutés" },
  { value: "blocked", label: "Bloqués" },
  { value: "error", label: "En échec" },
  { value: "alert", label: "Avec alerte du détecteur" },
];

function Detail({ e }: { e: AuditEntry }) {
  let args = "";
  try {
    args = JSON.stringify(e.args, null, 2);
  } catch {
    args = "";
  }
  return (
    <div className="detail">
      <div className="detail-head">
        <ServerTag server={e.server} />
        <code className="detail-tool">{e.tool}</code>
      </div>
      <dl className="facts">
        <div>
          <dt>Heure</dt>
          <dd>{formatWhen(e.ts * 1000)}</dd>
        </div>
        <div>
          <dt>Pare-feu</dt>
          <dd>
            <DecisionBadge decision={e.decision} />
          </dd>
        </div>
        <div>
          <dt>Issue</dt>
          <dd>
            <OutcomeBadge outcome={e.outcome} />
          </dd>
        </div>
        <div>
          <dt>Raison</dt>
          <dd>{e.reason || "—"}</dd>
        </div>
        <div>
          <dt>Détecteur</dt>
          <dd>{e.findings.length ? `${e.findings.join(", ")} (contenu retiré)` : "Aucun motif connu détecté"}</dd>
        </div>
      </dl>
      <p className="detail-label">Arguments demandés par le modèle</p>
      <pre className="code-block">{args.length > 4000 ? `${args.slice(0, 4000)}…` : args || "{}"}</pre>
      <p className="muted small">
        Le journal ne contient jamais le résultat d&apos;un outil. Durée d&apos;exécution : non mesurée par l&apos;API.
      </p>
    </div>
  );
}

export default function ActivityView() {
  const audit = useAudit(5000);
  const [server, setServer] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const list = filterAudit(audit.entries, { server, outcome, query });
  const stats = summarize(audit.entries);
  const servers = [...new Set(audit.entries.map((e) => e.server))];
  const current = selected !== null ? list[selected] : undefined;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Contrôle"
        title="Observatoire"
        lead="Chaque appel d'outil demandé par l'agent, avec la décision du pare-feu et son issue. Journal en mémoire de l'API depuis son démarrage."
        actions={
          <button type="button" className="btn btn-secondary btn-small" onClick={audit.refresh}>
            <IconRefresh size={15} /> Actualiser
          </button>
        }
      />
      <div className="stats stats-band">
        <Stat label="Appels" value={stats.calls} />
        <Stat label="Exécutés" value={stats.executed} tone="ok" />
        <Stat label="Bloqués" value={stats.blocked} tone={stats.blocked ? "warn" : undefined} />
        <Stat label="En échec" value={stats.errors} tone={stats.errors ? "bad" : undefined} />
        <Stat label="Alertes" value={stats.alerts} tone={stats.alerts ? "bad" : undefined} />
      </div>

      <div className="split">
        <Card className="split-main">
          <div className="filters">
            <select
              value={server}
              onChange={(e) => {
                setServer(e.target.value);
                setSelected(null);
              }}
              aria-label="Serveur"
            >
              <option value="all">Tous les serveurs</option>
              {servers.map((s) => (
                <option key={s} value={s}>
                  {SERVER_LABEL[s] ?? s}
                </option>
              ))}
            </select>
            <select
              value={outcome}
              onChange={(e) => {
                setOutcome(e.target.value);
                setSelected(null);
              }}
              aria-label="Issue"
            >
              {OUTCOMES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelected(null);
              }}
              placeholder="Outil ou raison…"
              aria-label="Filtrer par outil ou raison"
            />
          </div>
          {!audit.loaded ? (
            <Skeleton lines={6} />
          ) : audit.failed ? (
            <Empty title="Journal indisponible">L&apos;API ne répond pas. Vérifiez que « run_api.py » tourne.</Empty>
          ) : list.length === 0 ? (
            <Empty icon={<IconPulse />} title={audit.entries.length ? "Aucun appel ne correspond aux filtres" : "Aucun appel d'outil pour le moment"}>
              {audit.entries.length ? "Modifiez les filtres." : "Les appels apparaissent ici dès que l'agent utilise un outil."}
            </Empty>
          ) : (
            <ol className="audit-list timeline">
              {list.slice(0, 300).map((e, i) => (
                <AuditRow key={`${e.ts}-${i}`} e={e} selected={i === selected} onOpen={() => setSelected(i === selected ? null : i)} />
              ))}
            </ol>
          )}
          {list.length > 300 && <p className="muted small">300 appels affichés sur {list.length} : affinez les filtres.</p>}
        </Card>
        <Card title="Détail de l'appel" className="split-side">
          {current ? <Detail e={current} /> : <Empty title="Sélectionnez un appel">Le détail (arguments, décision, détecteur) s&apos;affiche ici.</Empty>}
        </Card>
      </div>
    </div>
  );
}
