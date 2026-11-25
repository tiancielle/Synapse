// Thème : « light », « dark » ou « system » (suit le système). Choix mémorisé dans le navigateur.
// Appliqué AVANT le premier affichage par le script de layout.tsx (THEME_SCRIPT), puis par setTheme().
export type ThemeChoice = "light" | "dark" | "system";

export const THEME_KEY = "agentflow:theme";

export function readTheme(raw: string | null): ThemeChoice {
  return raw === "light" || raw === "dark" ? raw : "system";
}

/** Script exécuté pendant l'analyse du HTML : pose data-theme sur <html> sans flash. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

const listeners = new Set<() => void>();
let current: ThemeChoice | null = null;

export function getTheme(): ThemeChoice {
  if (current === null) {
    try {
      current = readTheme(window.localStorage.getItem(THEME_KEY));
    } catch {
      current = "system";
    }
  }
  return current;
}

export function getServerTheme(): ThemeChoice {
  return "system";
}

export function subscribeTheme(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function setTheme(choice: ThemeChoice) {
  current = choice;
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    if (choice === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // stockage indisponible : le thème s'applique quand même pour cette page
  }
  listeners.forEach((l) => l());
}
