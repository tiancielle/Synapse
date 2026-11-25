"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { getHealth } from "./api";
import type { Health } from "./types";

const POLL_MS = 15000;

export type HealthState = { health: Health | null; down: boolean; checked: boolean; refresh: () => Promise<void> };

/** État de l'API (/api/health), revérifié toutes les 15 s pour détecter un serveur éteint ou relancé. */
export function useHealthPolling(): HealthState {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [checked, setChecked] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setDown(false);
    } catch {
      setDown(true);
    } finally {
      setChecked(true);
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(() => void refresh(), 0); // première vérification juste après l'affichage
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  return { health, down, checked, refresh };
}

export const HealthContext = createContext<HealthState>({ health: null, down: false, checked: false, refresh: async () => {} });

/** Un seul sondage pour toute l'application (fourni par AppShell). */
export function useHealth(): HealthState {
  return useContext(HealthContext);
}
