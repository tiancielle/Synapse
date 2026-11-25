"use client";

import Link from "next/link";

import { IconLock } from "@/components/Icons";
import { Card, Chip, DecisionBadge, Empty, PageHeader, ServerIcon, Skeleton } from "@/components/ui";
import catalog from "@/lib/catalog.json";
import { useAudit } from "@/lib/hooks";
import { buildIntegrations, type Catalog, type Integration } from "@/lib/integrations";
import { formatAgo, RISK_LABEL } from "@/lib/labels";
import { useHealth } from "@/lib/useHealth";

export function ToolTable({ integration }: { integration: Integration }) {
  return (
    <div className="table-wrap">
      <table className="tools">
        <thead>
          <tr>
            <th scope="col">Outil</th>
            <th scope="col">Risque</th>
            <th scope="col">Permission</th>
            <th scope="col">Pare-feu</th>
            <th scope="col">Appels</th>
          </tr>
        </thead>
        <tbody>
          {integration.tools.map((t) => (
            <tr key={t.name} data-available={t.available}>
              <td>
                <span className="tool-name">
                  <code>{t.name}</code>
                  <span className="muted small">{t.label}</span>
                </span>
                {!t.available && integration.launched && (
                  <span className="tool-off">
                    <IconLock size={12} /> indisponible avec {integration.sourceLabel}
                  </span>
                )}
              </td>
              <td>
                <Chip tone={t.risk === "sensitive" ? "warn" : t.risk === "soft_write" ? "info" : undefined}>{RISK_LABEL[t.risk]}</Chip>
              </td>
              <td>
                <code className="scope">{t.scope}</code>
              </td>
              <td>
                <DecisionBadge decision={t.decision} />
              </td>
              <td className="num">{t.calls}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function IntegrationStatus({ i }: { i: Integration }) {
  return (
    <div className="int-status">
      <span className="status-dot" data-state={i.launched ? "up" : "off"} />
      <span>{i.launched ? "Serveur lancé" : "Serveur non lancé"}</span>
      {i.launched && <Chip tone={i.real ? "accent" : undefined}>{i.real ? `${i.sourceLabel} · réel` : "Données de test"}</Chip>}
      {i.activity.errors > 0 && <Chip tone="bad">{i.activity.errors} échec{i.activity.errors > 1 ? "s" : ""}</Chip>}
      {i.activity.last !== null && <span className="muted small">dernier appel {formatAgo(i.activity.last * 1000)}</span>}
    </div>
  );
}

export default function IntegrationsView() {
  const { health, checked, down } = useHealth();
  const audit = useAudit();
  const integrations = buildIntegrations(catalog as Catalog, health, audit.entries);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Intégrations"
        title="Explorateur MCP"
        lead={
          <>
            Serveurs MCP et outils réellement exposés à l&apos;agent, avec la décision que le pare-feu applique à chacun. Un outil absent
            du registre est refusé par défaut.
          </>
        }
      />
      {!checked ? (
        <Skeleton lines={6} />
      ) : down || !health ? (
        <Card>
          <Empty title="API injoignable">L&apos;état des serveurs vient de l&apos;API : lancez « run_api.py ».</Empty>
        </Card>
      ) : (
        <div className="stack">
          {integrations.map((i) => (
            <Card
              key={i.name}
              className="int-card"
              title={
                <span className="int-title">
                  <span className="int-icon">
                    <ServerIcon server={i.name} size={18} />
                  </span>
                  {i.label}
                  <code className="int-code">{i.name}</code>
                </span>
              }
              action={
                <Link href={`/${i.name}`} className="card-link">
                  Ouvrir
                </Link>
              }
            >
              <p className="muted">{i.description}</p>
              <IntegrationStatus i={i} />
              {i.note && <p className="notice notice-muted">{i.note}</p>}
              <ToolTable integration={i} />
            </Card>
          ))}
          <p className="page-note">
            Catalogue d&apos;affichage aligné sur le registre du pare-feu (core/registry.py), vérifié par un test. Lancement des serveurs :
            option « --servers » de run_api.py.
          </p>
        </div>
      )}
    </div>
  );
}
