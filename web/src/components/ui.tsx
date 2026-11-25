import Link from "next/link";
import type { ReactNode } from "react";

import { IconBranch, IconCalendar, IconMail, IconPlug } from "@/components/Icons";
import { DECISION_LABEL, OUTCOME_LABEL, SERVER_LABEL } from "@/lib/labels";
import type { Decision, ToolOutcome } from "@/lib/types";

// ───────── Primitives du système de design AgentFlow ─────────

export function PageHeader({ eyebrow, title, lead, actions }: { eyebrow: string; title: string; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="page-head-text">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        {lead && <p className="page-lead">{lead}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, action, children, className, tone }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; tone?: "accent" }) {
  return (
    <section className={`card${tone ? ` card-${tone}` : ""}${className ? ` ${className}` : ""}`}>
      {(title || action) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Chip({ tone, children, title }: { tone?: "ok" | "warn" | "bad" | "info" | "accent"; children: ReactNode; title?: string }) {
  return (
    <span className={`chip${tone ? ` chip-${tone}` : ""}`} title={title}>
      {children}
    </span>
  );
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <span className="empty-icon">{icon}</span>}
      <p className="empty-title">{title}</p>
      {children && <p className="empty-text">{children}</p>}
      {action}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "ok" | "warn" | "bad" }) {
  return (
    <div className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeletons" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton" />
      ))}
    </div>
  );
}

const DECISION_TONE: Record<Decision, "ok" | "info" | "warn" | "bad"> = { auto: "ok", notify: "info", confirm: "warn", deny: "bad" };
export function DecisionBadge({ decision }: { decision: Decision }) {
  return <Chip tone={DECISION_TONE[decision]}>{DECISION_LABEL[decision]}</Chip>;
}

const OUTCOME_TONE: Record<ToolOutcome, "ok" | "warn" | "bad"> = { executed: "ok", blocked: "warn", error: "bad" };
export function OutcomeBadge({ outcome }: { outcome: ToolOutcome }) {
  return <Chip tone={OUTCOME_TONE[outcome]}>{OUTCOME_LABEL[outcome]}</Chip>;
}

export function ServerIcon({ server, size = 16 }: { server: string; size?: number }) {
  if (server === "calendar") return <IconCalendar size={size} />;
  if (server === "mail") return <IconMail size={size} />;
  if (server === "github") return <IconBranch size={size} />;
  return <IconPlug size={size} />;
}

export function ServerTag({ server }: { server: string }) {
  return (
    <span className="server-tag" data-server={server}>
      <ServerIcon server={server} size={13} />
      {SERVER_LABEL[server] ?? server}
    </span>
  );
}

export function ButtonLink({ href, children, variant = "secondary" }: { href: string; children: ReactNode; variant?: "primary" | "secondary" | "ghost" }) {
  return (
    <Link href={href} className={`btn btn-${variant}`}>
      {children}
    </Link>
  );
}

/** Repère de plan (détail « blueprint ») : numéro + trait fin. */
export function Mark({ n }: { n: string }) {
  return (
    <span className="mark" aria-hidden="true">
      {n}
    </span>
  );
}
