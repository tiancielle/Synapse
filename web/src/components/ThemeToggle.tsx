"use client";

import type { ReactNode } from "react";

import { IconMonitor, IconMoon, IconSun } from "@/components/Icons";
import { useTheme } from "@/lib/hooks";
import { setTheme, type ThemeChoice } from "@/lib/theme";

const NEXT: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<ThemeChoice, string> = { system: "Thème du système", light: "Thème clair", dark: "Thème sombre" };

/** Bouton compact : système → clair → sombre. Le choix détaillé est dans Réglages. */
export default function ThemeToggle() {
  const theme = useTheme();
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme(NEXT[theme])}
      aria-label={`${LABEL[theme]} (cliquer pour : ${LABEL[NEXT[theme]].toLowerCase()})`}
      title={LABEL[theme]}
    >
      {theme === "light" ? <IconSun /> : theme === "dark" ? <IconMoon /> : <IconMonitor />}
    </button>
  );
}

export function ThemeSelector() {
  const theme = useTheme();
  const options: { value: ThemeChoice; label: string; icon: ReactNode }[] = [
    { value: "light", label: "Clair", icon: <IconSun size={16} /> },
    { value: "dark", label: "Sombre", icon: <IconMoon size={16} /> },
    { value: "system", label: "Système", icon: <IconMonitor size={16} /> },
  ];
  return (
    <div className="segmented" role="radiogroup" aria-label="Thème">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={theme === o.value} onClick={() => setTheme(o.value)}>
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}
