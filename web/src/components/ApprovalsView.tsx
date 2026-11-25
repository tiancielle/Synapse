"use client";

import Link from "next/link";

import ConfirmCard from "@/components/ConfirmCard";
import { IconCheck, IconShield } from "@/components/Icons";
import { Card, Chip, Empty, PageHeader, ServerTag, Skeleton } from "@/components/ui";
import { useAudit, useConversations, useRunner } from "@/lib/hooks";
import { approvalHistory, pendingApprovals } from "@/lib/insights";
import { argsPreview, formatWhen } from "@/lib/labels";
import { decide, setActive } from "@/lib/runner";
import { useHealth } from "@/lib/useHealth";

export default function ApprovalsView() {
  const conversations = useConversations();
  const { run } = useRunner();
  const audit = useAudit();
  const { health } = useHealth();
  const pending = pendingApprovals(conversations);
  const history = approvalHistory(audit.entries);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Contrôle"
        title="Approbations"
        lead="Les actions classées sensibles par le registre (envoi, suppression) attendent votre décision. Le serveur reprend l'exécution suspendue selon votre réponse."
      />

      {health?.defenses === "aucune" && (
        <p className="notice notice-error" role="status">
          Préréglage « Aucune défense » : le pare-feu ne demande aucune confirmation (mode de comparaison pour l&apos;évaluation).
        </p>
      )}

      <section className="stack">
        <h2 className="section-title">En attente{pending.length > 0 && <Chip tone="warn">{pending.length}</Chip>}</h2>
        {conversations === null ? (
          <Skeleton lines={2} />
        ) : pending.length === 0 ? (
          <Card>
            <Empty icon={<IconCheck />} title="Aucune action en attente">
              Quand l&apos;agent demande une action sensible, elle apparaît ici et dans sa conversation.
            </Empty>
          </Card>
        ) : (
          pending.map((p, index) => (
            <div key={p.convId} className="approval">
              <div className="approval-context">
                <span className="muted small">Conversation</span>
                <Link
                  href="/studio"
                  className="approval-conv"
                  onClick={() => setActive(p.convId)}
                >
                  {p.title}
                </Link>
                {p.request.server && <ServerTag server={p.request.server} />}
              </div>
              <ConfirmCard request={p.request} busy={run !== null} autoFocus={index === 0} onDecision={(ok) => void decide(p.convId, ok)} />
            </div>
          ))
        )}
      </section>

      <Card title="Historique des décisions" action={<span className="muted small">depuis le démarrage de l&apos;API</span>}>
        {!audit.loaded ? (
          <Skeleton lines={3} />
        ) : audit.failed ? (
          <Empty title="Historique indisponible">L&apos;API ne répond pas.</Empty>
        ) : history.length === 0 ? (
          <Empty icon={<IconShield />} title="Aucune action sensible pour le moment" />
        ) : (
          <ul className="audit-list">
            {history.map((h, i) => (
              <li key={`${h.ts}-${i}`} className="audit-row">
                <span className="audit-time">{formatWhen(h.ts * 1000)}</span>
                <ServerTag server={h.server} />
                <code className="audit-tool">{h.tool}</code>
                <span className="audit-args">{argsPreview(h.args)}</span>
                <span className="audit-badges">
                  {h.verdict === "approved" ? <Chip tone="ok">Autorisée</Chip> : <Chip tone="warn">Refusée</Chip>}
                  {h.outcome === "error" && <Chip tone="bad">en échec</Chip>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
