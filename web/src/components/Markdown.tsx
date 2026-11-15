import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Rendu Markdown SÛR : le texte vient du modèle (donc potentiellement d'une injection de prompt).
 * - pas de HTML brut (react-markdown sans rehype-raw, et `skipHtml`) ;
 * - AUCUNE image : une image distante enverrait des données à un site tiers au simple affichage ;
 * - liens http/https uniquement, ouverts dans un nouvel onglet, avec l'hôte visible au survol.
 */
function safeUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? url : "";
  } catch {
    return "";
  }
}

const components: Components = {
  a({ href, children }) {
    const url = safeUrl(href ?? "");
    if (!url) return <span>{children}</span>;
    return (
      <a href={url} target="_blank" rel="noopener noreferrer nofollow" title={new URL(url).host}>
        {children}
      </a>
    );
  },
  table({ children }) {
    return (
      <div className="md-table">
        <table>{children}</table>
      </div>
    );
  },
};

function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={safeUrl}
        disallowedElements={["img"]}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default memo(Markdown);
