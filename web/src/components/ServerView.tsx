"use client";

import { IntegrationStatus, ToolTable } from "@/components/IntegrationsView";
import { AuditRow, PromptList } from "@/components/shared";
import { Card, Empty, PageHeader, ServerIcon, Skeleton } from "@/components/ui";
import catalog from "@/lib/catalog.json";
import { useAudit } from "@/lib/hooks";
import { buildIntegrations, type Catalog } from "@/lib/integrations";
import { PROMPTS } from "@/lib/prompts";
import type { ServerName } from "@/lib/types";
import { useHealth } from "@/lib/useHealth";

const LEAD: Record<ServerName, string> = {
  calendar: "Votre agenda, consulté par l'agent. L'API n'expose pas de lecture directe des événements : posez votre question, l'agent appelle les outils du calendrier.",
  mail: "Votre messagerie, consultée par l'agent. L'API n'expose pas de lecture directe des mails : posez votre question, l'agent cherche et lit pour vous.",
  github: "Vos dépôts et les projets publics, consultés par l'agent en lecture seule. Posez votre question : l'agent choisit les outils GitHub.",
};

/** Page d'une intégration : état réel, questions prêtes à envoyer, outils, activité récente du serveur. */
export default function ServerView({ server }: { server: ServerName }) {
  const { health, checked, down } = useHealth();
  const audit = useAudit();
  const i = buildIntegrations(catalog as Catalog, health, audit.entries).find((x) => x.name === server);
  if (!i) return null;
  const recent = audit.entries.filter((e) => e.server === server).sort((a, b) => b.ts - a.ts).slice(0, 8);

  return (
    <div className="page">
      <PageHeader eyebrow="Intégrations" title={i.label} lead={LEAD[server]} />
      {!checked ? (
        <Skeleton lines={4} />
      ) : down || !health ? (
        <Card>
          <Empty title="API injoignable">Lancez « run_api.py » pour utiliser cette intégration.</Empty>
        </Card>
      ) : (
        <div className="grid">
          <Card title="État" className="span-12">
            <IntegrationStatus i={i} />
            {i.note && <p className="notice notice-muted">{i.note}</p>}
            {!i.launched && (
              <p className="notice notice-warn">
                Ce serveur n&apos;est pas lancé : relancez l&apos;API avec « --servers » incluant « {server} » (par défaut, tous les serveurs
                sont lancés).
              </p>
            )}
          </Card>
          <Card title="Demander à l'agent" className="span-5">
            {i.launched ? (
              <PromptList prompts={PROMPTS[server]} server={server} />
            ) : (
              <Empty icon={<ServerIcon server={server} />} title="Serveur non lancé" />
            )}
          </Card>
          <Card title="Activité récente" className="span-7">
            {!audit.loaded ? (
              <Skeleton lines={3} />
            ) : recent.length === 0 ? (
              <Empty title="Aucun appel pour le moment">Les appels de l&apos;agent à ce serveur apparaîtront ici.</Empty>
            ) : (
              <ul className="audit-list">
                {recent.map((e, n) => (
                  <AuditRow key={`${e.ts}-${n}`} e={e} />
                ))}
              </ul>
            )}
          </Card>
          <Card title="Outils et permissions" className="span-12">
            <ToolTable integration={i} />
          </Card>
        </div>
      )}
    </div>
  );
}
