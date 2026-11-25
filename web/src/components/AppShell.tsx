"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import CommandPalette from "@/components/CommandPalette";
import {
  IconBell,
  IconBranch,
  IconCalendar,
  IconChat,
  IconCheck,
  IconGear,
  IconHome,
  IconMail,
  IconMenu,
  IconPlug,
  IconPulse,
  IconSearch,
  IconShield,
  IconSpark,
  LogoMark,
} from "@/components/Icons";
import ThemeToggle from "@/components/ThemeToggle";
import { useConversations, useRunner } from "@/lib/hooks";
import { pendingApprovals } from "@/lib/insights";
import { DEFENSES_LABEL } from "@/lib/labels";
import { activeKey, GROUP_LABEL, NAV, type NavKey } from "@/lib/nav";
import { setOnFailure } from "@/lib/runner";
import { APP_NAME } from "@/lib/types";
import { HealthContext, useHealthPolling } from "@/lib/useHealth";

const ICONS: Record<NavKey, ReactNode> = {
  overview: <IconHome />,
  studio: <IconSpark />,
  conversations: <IconChat />,
  activity: <IconPulse />,
  approvals: <IconCheck />,
  integrations: <IconPlug />,
  mail: <IconMail />,
  calendar: <IconCalendar />,
  github: <IconBranch />,
  settings: <IconGear />,
};

export default function AppShell({ children }: { children: ReactNode }) {
  const healthState = useHealthPolling();
  const { health, down, checked, refresh } = healthState;
  const pathname = usePathname();
  const current = activeKey(pathname);
  const conversations = useConversations();
  const { run } = useRunner();
  const pending = pendingApprovals(conversations).length;
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // une exécution échoue : l'API est peut-être éteinte, on revérifie tout de suite
  useEffect(() => {
    setOnFailure(() => void refresh());
    return () => setOnFailure(null);
  }, [refresh]);

  // Ctrl+K / ⌘K : palette de commandes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const groups = (["espace", "controle", "integrations", "systeme"] as const).map((g) => ({ g, items: NAV.filter((n) => n.group === g) }));

  return (
    <HealthContext.Provider value={healthState}>
      <div className="app" data-full={current === "studio"}>
        {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />}
        <aside className="nav" data-open={navOpen} aria-label="Navigation principale">
          <Link href="/" className="brand" onClick={() => setNavOpen(false)}>
            <LogoMark size={30} />
            <span className="brand-text">
              <span className="brand-name">{APP_NAME}</span>
              <span className="brand-sub">Espace agentique</span>
            </span>
          </Link>

          <button type="button" className="nav-command" onClick={() => setPaletteOpen(true)}>
            <IconSearch size={16} />
            <span>Demander ou naviguer</span>
            <kbd>Ctrl K</kbd>
          </button>

          <nav className="nav-groups">
            {groups.map(({ g, items }) => (
              <div key={g} className="nav-group">
                <p className="nav-label">{GROUP_LABEL[g]}</p>
                <ul>
                  {items.map((n) => (
                    <li key={n.key}>
                      <Link
                        href={n.href}
                        className="nav-link"
                        aria-current={current === n.key ? "page" : undefined}
                        onClick={() => setNavOpen(false)}
                        title={n.hint}
                      >
                        {ICONS[n.key]}
                        <span className="nav-text">{n.label}</span>
                        {n.key === "approvals" && pending > 0 && <span className="nav-count nav-count-warn">{pending}</span>}
                        {n.key === "studio" && run && <span className="nav-live" title="Exécution en cours" />}
                        {n.key === "conversations" && conversations && conversations.length > 0 && (
                          <span className="nav-count">{conversations.length}</span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>

          <div className="nav-foot">
            <span className="status-dot" data-state={!checked ? "unknown" : down ? "down" : "up"} />
            <span>{!checked ? "Connexion à l'API…" : down ? "API injoignable" : "API locale connectée"}</span>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <button type="button" className="icon-btn menu-btn" onClick={() => setNavOpen(true)} aria-label="Ouvrir la navigation">
              <IconMenu />
            </button>
            <button type="button" className="topbar-search" onClick={() => setPaletteOpen(true)}>
              <IconSearch size={16} />
              <span>Demander à l&apos;agent ou aller à une page…</span>
              <kbd>Ctrl K</kbd>
            </button>
            <div className="topbar-right">
              {down ? (
                <>
                  <span className="chip chip-bad">API injoignable</span>
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => void refresh()}>
                    Réessayer
                  </button>
                </>
              ) : (
                health && (
                  <div className="chips" aria-label="État du système">
                    {health.model === "demo" ? (
                      <span className="chip chip-warn">Mode démo · réponses simulées</span>
                    ) : (
                      <span className="chip chip-quiet">{health.llm ?? "Modèle réel"}</span>
                    )}
                    <span
                      className={`chip ${health.defenses === "aucune" ? "chip-bad" : health.defenses === "inconnu" ? "chip-warn" : "chip-ok"}`}
                    >
                      <IconShield size={13} /> {DEFENSES_LABEL[health.defenses]}
                    </span>
                  </div>
                )
              )}
              <Link
                href="/approvals"
                className="icon-btn bell"
                aria-label={pending ? `${pending} approbation${pending > 1 ? "s" : ""} en attente` : "Approbations : rien en attente"}
                title={pending ? `${pending} en attente` : "Aucune approbation en attente"}
              >
                <IconBell />
                {pending > 0 && <span className="bell-dot">{pending}</span>}
              </Link>
              <ThemeToggle />
            </div>
          </header>
          <main className="content" id="contenu">
            {children}
          </main>
        </div>
        {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
      </div>
    </HealthContext.Provider>
  );
}
