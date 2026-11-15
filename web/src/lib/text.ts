/** Convertit une valeur inconnue en texte (le modèle peut renvoyer autre chose qu'une chaîne). */
export function toText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    // blocs de contenu : [{type:"text", text:"…"}, "…"]
    return value
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) return toText((part as { text: unknown }).text);
        return "";
      })
      .join("");
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Retire les blocs <think>…</think> que certains modèles laissent dans leur réponse (y compris un bloc non fermé). */
export function stripThinking(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/gi, "").replace(/<think>[\s\S]*$/i, "").trimStart();
}

/** Raccourcit un texte pour l'affichage (les contenus venant des outils sont non fiables et peuvent être longs). */
export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
