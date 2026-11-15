import { IconMenu, IconPanel, IconShield } from "@/components/Icons";
import { API_URL } from "@/lib/api";
import type { Health } from "@/lib/types";

type Props = {
  title: string;
  health: Health | null;
  down: boolean;
  panelOpen: boolean;
  onMenu: () => void;
  onTogglePanel: () => void;
  onRetry: () => void;
};

const SOURCE = { test: "Données de test", google: "Google Calendar · lecture seule" } as const;
const DEFENSES = { toutes: "Défenses complètes", registre: "Registre de risques seul", aucune: "Aucune défense" } as const;

function Chip({ tone, children }: { tone?: "ok" | "warn" | "bad"; children: React.ReactNode }) {
  return <span className={`chip${tone ? ` chip-${tone}` : ""}`}>{children}</span>;
}

export default function TopBar({ title, health, down, panelOpen, onMenu, onTogglePanel, onRetry }: Props) {
  return (
    <header className="topbar">
      <button type="button" className="icon-btn menu-btn" onClick={onMenu} aria-label="Ouvrir la liste des conversations">
        <IconMenu />
      </button>
      <h1 className="topbar-title">{title}</h1>

      <div className="topbar-right">
        {down && (
          <>
            <Chip tone="bad">API injoignable</Chip>
            <button type="button" className="btn btn-ghost btn-small" onClick={onRetry} title={API_URL}>
              Réessayer
            </button>
          </>
        )}
        {!down && health && (
          <div className="chips" aria-label="État du système">
            {health.model === "demo" ? (
              <Chip tone="warn">Mode démo · réponses simulées</Chip>
            ) : (
              <Chip>{health.llm ?? "Modèle réel"}</Chip>
            )}
            <Chip>{SOURCE[health.source]}</Chip>
            <Chip tone={health.defenses === "aucune" ? "bad" : "ok"}>
              <IconShield size={13} /> {DEFENSES[health.defenses]}
            </Chip>
          </div>
        )}
        <button
          type="button"
          className="icon-btn"
          onClick={onTogglePanel}
          aria-pressed={panelOpen}
          aria-label={panelOpen ? "Masquer le panneau de progression" : "Afficher le panneau de progression"}
          title="Progression"
        >
          <IconPanel />
        </button>
      </div>
    </header>
  );
}
