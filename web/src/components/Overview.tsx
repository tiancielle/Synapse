"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { IconCheck, IconPulse, IconShield } from "@/components/Icons";
import { AuditRow, CommandBar, PromptList } from "@/components/shared";
import { ButtonLink, Card, Chip, Empty, Mark, ServerIcon, Skeleton, Stat } from "@/components/ui";
import catalog from "@/lib/catalog.json";
import { useAudit, useConversations, useRunner } from "@/lib/hooks";
import { pendingApprovals } from "@/lib/insights";
import { buildIntegrations, summarize, type Catalog } from "@/lib/integrations";
import { DEFENSES_DETAIL, DEFENSES_LABEL, formatAgo } from "@/lib/labels";
import { suggestionsFor } from "@/lib/prompts";
import { useHealth } from "@/lib/useHealth";

const noop = () => () => {};
function greeting(): string {
  const h = new Date().getHours();
  return h >= 18 || h < 5 ? "Bonsoir" : "Bonjour";
}

export default function Overview() {
  const hello = useSyncExternalStore(noop, greeting, () => "Bonjour"); // heure du navigateur, jamais celle du serveur
  const { health, down, checked } = useHealth();
  const audit = useAudit();
  const conversations = useConversations();
  const { run } = useRunner();
  const pending = pendingApprovals(conversations);
  const stats = summarize(audit.entries);
  const integrations = buildIntegrations(catalog as Catalog, health, audit.entries);
  const recent = [...audit.entries].sort((a, b) => b.ts - a.ts).slice(0, 6);
  const prompts = suggestionsFor(health?.servers ?? [], 4);

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <p className="eyebrow">Vue d&apos;ensemble</p>
        <h1 className="hero-title">
          {hello}. <em>Que confions-nous à l&apos;agent ?</em>
        </h1>
        <p className="hero-lead">
          Une question lance une conversation dans le Studio. Chaque appel d&apos;outil passe par le pare-feu ; les actions sensibles
          attendent votre accord.
        </p>
        <CommandBar placeholder="Ex. Qu'ai-je poussé cette semaine sur GitHub ?" />
      </section>

      <div className="grid grid-overview">
        <Card title={<><Mark n="01" /> Agent</>} className="span-4">
          {!checked ? (
            <Skeleton lines={3} />
          ) : down || !health ? (
            <Empty title="API injoignable">Lancez « run_api.py » dans un terminal, puis rechargez la page.</Empty>
          ) : (
            <div className="agent-status">
              <div className="agent-status-row">
                <span className="status-dot" data-state={run ? "busy" : "up"} />
                <strong>{run ? "En cours d'exécution" : "Disponible"}</strong>
              </div>
              <dl className="facts">
                <div>
                  <dt>Modèle</dt>
                  <dd>{health.model === "demo" ? "Démo (réponses simulées)" : (health.llm ?? "Modèle réel")}</dd>
                </div>
                <div>
                  <dt>Défenses</dt>
                  <dd>
                    <IconShield size={13} /> {DEFENSES_LABEL[health.defenses]}
                  </dd>
                </div>
              </dl>
              <p className="muted small">{DEFENSES_DETAIL[health.defenses]}</p>
            </div>
          )}
        </Card>

        <Card title={<><Mark n="02" /> Intégrations</>} action={<Link href="/integrations" className="card-link">Explorer</Link>} className="span-4">
          {!health ? (
            checked ? <Empty title="État inconnu">L&apos;API ne répond pas.</Empty> : <Skeleton lines={3} />
          ) : (
            <ul className="int-mini">
              {integrations.map((i) => (
                <li key={i.name} data-launched={i.launched}>
                  <span className="int-mini-icon">
                    <ServerIcon server={i.name} />
                  </span>
                  <span className="int-mini-text">
                    <span className="int-mini-name">{i.label}</span>
                    <span className="int-mini-sub">{i.launched ? i.sourceLabel : "Non lancé"}</span>
                  </span>
                  {i.launched ? <Chip tone={i.real ? "accent" : undefined}>{i.real ? "réel" : "test"}</Chip> : <Chip>arrêté</Chip>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title={<><Mark n="03" /> Approbations</>}
          action={<Link href="/approvals" className="card-link">Ouvrir</Link>}
          className="span-4"
          tone={pending.length ? "accent" : undefined}
        >
          {conversations === null ? (
            <Skeleton lines={2} />
          ) : pending.length === 0 ? (
            <Empty icon={<IconCheck />} title="Rien en attente">Les actions sensibles demandées par l&apos;agent apparaîtront ici.</Empty>
          ) : (
            <ul className="pending-mini">
              {pending.slice(0, 3).map((p) => (
                <li key={p.convId}>
                  <code>{p.request.tool}</code>
                  <span className="muted small">{p.title}</span>
                </li>
              ))}
              <li>
                <ButtonLink href="/approvals" variant="primary">
                  Décider ({pending.length})
                </ButtonLink>
              </li>
            </ul>
          )}
        </Card>

        <Card title={<><Mark n="04" /> Exécution depuis le démarrage de l&apos;API</>} className="span-8">
          {!audit.loaded ? (
            <Skeleton lines={2} />
          ) : audit.failed ? (
            <Empty title="Journal indisponible">L&apos;API ne répond pas.</Empty>
          ) : (
            <div className="stats">
              <Stat label="Appels d'outils" value={stats.calls} />
              <Stat label="Exécutés" value={stats.executed} tone="ok" />
              <Stat label="Bloqués" value={stats.blocked} tone={stats.blocked ? "warn" : undefined} />
              <Stat label="En échec" value={stats.errors} tone={stats.errors ? "bad" : undefined} />
              <Stat label="Alertes du détecteur" value={stats.alerts} tone={stats.alerts ? "bad" : undefined} hint="Motifs connus, retirés des résultats" />
            </div>
          )}
          <p className="muted small card-foot">
            Source : journal d&apos;audit en mémoire de l&apos;API, remis à zéro à chaque redémarrage.
            {stats.last !== null && ` Dernier appel ${formatAgo(stats.last * 1000)}.`}
          </p>
        </Card>

        <Card title={<><Mark n="05" /> Actions rapides</>} className="span-4">
          {prompts.length ? <PromptList prompts={prompts} /> : <Empty title="Aucun serveur lancé">Les raccourcis dépendent des serveurs lancés.</Empty>}
        </Card>

        <Card title={<><Mark n="06" /> Activité récente</>} action={<Link href="/activity" className="card-link">Observatoire</Link>} className="span-12">
          {!audit.loaded ? (
            <Skeleton lines={4} />
          ) : recent.length === 0 ? (
            <Empty icon={<IconPulse />} title="Aucun appel d'outil pour le moment">
              Posez une question à l&apos;agent : chaque appel d&apos;outil sera journalisé ici, avec la décision du pare-feu.
            </Empty>
          ) : (
            <ul className="audit-list">
              {recent.map((e, i) => (
                <AuditRow key={`${e.ts}-${i}`} e={e} />
              ))}
            </ul>
          )}
        </Card>
      </div>
      <p className="page-note">
        Prochains rendez-vous et derniers mails : l&apos;API n&apos;expose pas de lecture directe ; demandez-les à l&apos;agent (actions
        rapides).
      </p>
    </div>
  );
}
