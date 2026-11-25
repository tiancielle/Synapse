"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { getAudit } from "./api";
import { getRunner, getServerRunner, subscribeRunner } from "./runner";
import { getServerSnapshot, getSnapshot, subscribe } from "./storage";
import { getServerTheme, getTheme, subscribeTheme } from "./theme";
import type { AuditEntry } from "./types";

/** Conversations du navigateur (null tant qu'elles ne sont pas lues : jamais pendant le rendu serveur). */
export function useConversations() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function useRunner() {
  return useSyncExternalStore(subscribeRunner, getRunner, getServerRunner);
}

export function useTheme() {
  return useSyncExternalStore(subscribeTheme, getTheme, getServerTheme);
}

export type AuditState = { entries: AuditEntry[]; loaded: boolean; failed: boolean; refresh: () => void };

/** Journal d'audit de l'API, relu toutes les `pollMs` ms tant que la page est affichée. */
export function useAudit(pollMs = 8000): AuditState {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = useRunner().run;

  const refresh = useCallback(async () => {
    try {
      setEntries(await getAudit());
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(() => void refresh(), 0);
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, pollMs);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh, pollMs]);

  // une exécution vient de se terminer : le journal a changé
  useEffect(() => {
    if (run === null) {
      const t = setTimeout(() => void refresh(), 300);
      return () => clearTimeout(t);
    }
  }, [run, refresh]);

  return { entries, loaded, failed, refresh: () => void refresh() };
}
