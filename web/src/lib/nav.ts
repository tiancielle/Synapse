// Plan du site : utilisé par la navigation latérale et par la palette de commandes.
export type NavKey = "overview" | "studio" | "conversations" | "activity" | "approvals" | "integrations" | "mail" | "calendar" | "github" | "settings";

export type NavItem = { key: NavKey; href: string; label: string; hint: string; group: "espace" | "controle" | "integrations" | "systeme" };

export const NAV: NavItem[] = [
  { key: "overview", href: "/", label: "Vue d'ensemble", hint: "État de l'agent, activité et raccourcis", group: "espace" },
  { key: "studio", href: "/studio", label: "Studio de l'agent", hint: "Converser avec l'agent et suivre son exécution", group: "espace" },
  { key: "conversations", href: "/conversations", label: "Conversations", hint: "Historique, recherche et gestion", group: "espace" },
  { key: "activity", href: "/activity", label: "Observatoire", hint: "Journal d'audit des appels d'outils", group: "controle" },
  { key: "approvals", href: "/approvals", label: "Approbations", hint: "Actions en attente de votre décision", group: "controle" },
  { key: "integrations", href: "/integrations", label: "Explorateur MCP", hint: "Serveurs, outils et permissions", group: "integrations" },
  { key: "mail", href: "/mail", label: "Mail", hint: "Messagerie, via l'agent", group: "integrations" },
  { key: "calendar", href: "/calendar", label: "Calendrier", hint: "Agenda, via l'agent", group: "integrations" },
  { key: "github", href: "/github", label: "GitHub", hint: "Dépôts et projets, via l'agent", group: "integrations" },
  { key: "settings", href: "/settings", label: "Réglages", hint: "Thème, connexion à l'API, données locales", group: "systeme" },
];

export const GROUP_LABEL = { espace: "Espace de travail", controle: "Contrôle", integrations: "Intégrations", systeme: "Système" } as const;

export function activeKey(pathname: string): NavKey {
  const hit = NAV.filter((n) => n.href !== "/" && (pathname === n.href || pathname.startsWith(`${n.href}/`)));
  return hit[0]?.key ?? "overview";
}
