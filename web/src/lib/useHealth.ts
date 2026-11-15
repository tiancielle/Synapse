"use client";

import { useCallback, useEffect, useState } from "react";

import { getHealth } from "./api";
import type { Health } from "./types";

const POLL_MS = 15000;

/** État de l'API (/api/health), revérifié toutes les 15 s pour détecter un serveur éteint ou relancé. */
export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setDown(false);
    } catch {
      setDown(true);
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

  return { health, down, refresh };
}
