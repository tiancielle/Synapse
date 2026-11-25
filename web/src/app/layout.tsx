import type { Metadata, Viewport } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

import AppShell from "@/components/AppShell";
import { THEME_SCRIPT } from "@/lib/theme";
import { APP_NAME } from "@/lib/types";

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: "Espace de travail agentique multi-outils (MCP), sous le contrôle d'un pare-feu et d'une validation humaine",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
};

/** Script de thème : exécuté pendant l'analyse du HTML (avant le premier affichage), ignoré lors des navigations. */
function ThemeScript() {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }}
    />
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>
        <a className="skip" href="#contenu">
          Aller au contenu
        </a>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
