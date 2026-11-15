/**
 * Panneau de droite. Étape 1 : coque vide avec ses états « rien pour le moment ».
 * Étape 2 : « Progression » (5 étapes avec point d'état) et « Utilisés dans cette session » seront alimentés par les événements.
 */
export default function SidePanel() {
  return (
    <aside className="sidepanel" aria-label="Progression et outils utilisés">
      <section className="panel-section">
        <h2>Progression</h2>
        <p className="panel-empty">Les étapes de l&apos;agent apparaîtront ici pendant qu&apos;il travaille.</p>
      </section>
      <section className="panel-section">
        <h2>Utilisés dans cette session</h2>
        <p className="panel-empty">Aucun outil utilisé pour le moment.</p>
      </section>
    </aside>
  );
}
