import { parseSse } from "./sse";
import { localApiUrl, toAuditEntries, toHealth } from "./parse";
import type { AgentEvent, AuditEntry, Health } from "./types";

// L'API tourne en local ; le port peut être changé avec NEXT_PUBLIC_API_URL (fichier .env.local).
// Une adresse non locale est ignorée (règle 4 : API locale uniquement).
export const API_URL = localApiUrl(process.env.NEXT_PUBLIC_API_URL);

export type ApiErrorKind = "network" | "conflict" | "invalid" | "http" | "interrupted";

/** Erreur dont le message est déjà rédigé en français, prêt à être affiché. */
export class ApiError extends Error {
  kind: ApiErrorKind;
  constructor(kind: ApiErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${API_URL}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return toHealth(await res.json());
}

/** Journal d'audit de l'API (en mémoire depuis son démarrage). */
export async function getAudit(): Promise<AuditEntry[]> {
  const res = await fetch(`${API_URL}/api/audit`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return toAuditEntries(await res.json());
}

async function httpError(res: Response, path: string): Promise<ApiError> {
  if (res.status === 409) {
    return new ApiError(
      "conflict",
      path === "/api/confirm"
        ? "Cette demande de confirmation n'existe plus (le serveur a peut-être redémarré). Pose à nouveau ta question."
        : "Une confirmation est encore en attente pour cette conversation. Réponds-y d'abord, ou ouvre une nouvelle conversation.",
    );
  }
  if (res.status === 422) {
    return new ApiError("invalid", "L'API a refusé la requête : le message doit contenir entre 1 et 2000 caractères.");
  }
  if (res.status === 400) {
    return new ApiError("http", "L'API a refusé la requête (400). Ouvre l'interface via http://localhost:3000.");
  }
  return new ApiError("http", `Erreur du serveur (${res.status}). Consulte le terminal où tourne l'API.`);
}

/**
 * Envoie une requête POST et appelle `onEvent` pour chaque événement reçu en direct.
 * Lève une ApiError (message en français) en cas de problème ; le signal permet d'arrêter le flux.
 */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(
      "network",
      `Impossible de joindre l'API (${API_URL}). Vérifie que « python run_api.py » tourne dans un terminal et que tu utilises http://localhost:3000.`,
    );
  }

  if (!res.ok || !res.body) throw await httpError(res, path);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  const emit = (events: AgentEvent[]) => {
    for (const event of events) {
      if (event.type === "done") finished = true;
      onEvent(event);
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSse(buffer);
      buffer = parsed.rest;
      emit(parsed.events);
    }
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError("interrupted", "La connexion avec l'API a été interrompue pendant la réponse.");
  }

  emit(parseSse(`${buffer + decoder.decode()}\n\n`).events); // dernier message éventuel sans ligne vide finale
  if (!finished) {
    throw new ApiError("interrupted", "Le flux s'est terminé avant la fin de la réponse (le serveur a-t-il été arrêté ?).");
  }
}
