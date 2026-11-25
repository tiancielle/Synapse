"""GH-5 : les quatre questions d'exemple, en chaînes SCRIPTÉES à travers l'agent complet (serveur github seul).

Les modèles sont scriptés : ces tests vérifient la plomberie (outils, arguments, liste blanche, résultats vus
par le modèle), PAS qu'un vrai modèle choisirait ces appels.
"""
import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from agent.fakes import ScriptedLLM, tool_call
from agent.graph import run_agent
from agent.runtime import open_runtime

Y = "demo/projet-y"


def jouer(appels, defenses="toutes"):
    script = [AIMessage(content="Plan.")]
    script += [tool_call(f"github__{nom}", args, f"c{i}") for i, (nom, args) in enumerate(appels)]
    script += [AIMessage(content="Voici la réponse."), AIMessage(content="OK")]

    async def scenario():
        async with open_runtime(source="test", defenses=defenses, llm=ScriptedLLM(script), audit_path=None,
                                actifs=("github",)) as rt:
            result = await run_agent(rt.graph, "Question GitHub", "ex1")
            return rt, result
    rt, result = asyncio.run(scenario())
    issues = [(e["tool"], e["outcome"]) for e in rt.firewall.audit]
    vus = {m.name.split("__")[-1]: str(m.content) for m in result["messages"] if isinstance(m, ToolMessage)}
    return issues, vus


def test_exemple_version_poussee():
    """« Ai-je poussé la version v1.2 sur le projet Y ? »"""
    issues, vus = jouer([("lister_versions", {"depot": Y, "version": "v1.2"}),
                         ("lister_commits", {"depot": Y, "depuis": "2026-10-12", "jusqu_a": "2026-10-12"})])
    assert issues == [("lister_versions", "executed"), ("lister_commits", "executed")]
    assert '"v1.2"' in vus["lister_versions"] and "f7091b2" in vus["lister_versions"]
    assert "Version 1.2 : export ICS stable" in vus["lister_commits"]


def test_exemple_pull_requests_ouvertes_sur_tous_les_projets():
    """« Ai-je des pull requests ouvertes sur mes projets ? » (depot vide = toute la liste blanche)"""
    issues, vus = jouer([("lister_pull_requests", {"auteur": "etudiante-test"})])
    assert issues == [("lister_pull_requests", "executed")]
    assert Y in vus["lister_pull_requests"] and "Corrige le fuseau horaire" in vus["lister_pull_requests"]
    assert "demo/prive" not in vus["lister_pull_requests"]


def test_exemple_pousse_cette_semaine():
    """« Qu'ai-je poussé cette semaine ? » (commits filtrés par date, tous les dépôts)"""
    issues, vus = jouer([("lister_commits", {"depuis": "2026-10-12", "jusqu_a": "2026-10-18",
                                             "auteur": "etudiante-test"})])
    assert issues == [("lister_commits", "executed")]
    vu = vus["lister_commits"]
    assert "demo/agentflow-test" in vu and Y in vu
    assert "Version 1.1" not in vu                                    # 28 septembre : hors de la semaine


def test_exemple_quel_projet_parle_de_x_puis_readme():
    """« Dans quel projet est-il question d'export ICS ? » puis lecture du README du bon dépôt."""
    issues, vus = jouer([("lister_depots", {}), ("chercher_issues", {"requete": "export ICS"}),
                         ("lire_fichier", {"depot": Y, "chemin": "README.md"})])
    assert issues == [("lister_depots", "executed"), ("chercher_issues", "executed"), ("lire_fichier", "executed")]
    assert Y in vus["chercher_issues"] and "# Projet Y" in vus["lire_fichier"]


def test_exemple_chercher_un_cours_sur_tout_github():
    """« Je cherche un cours sur GitHub » : fiches publiques ; lire le dépôt trouvé reste refusé (liste blanche)."""
    issues, vus = jouer([("chercher_projets", {"requete": "cours git"}),
                         ("lire_fichier", {"depot": "open-cours/cours-git-debutant", "chemin": "README.md"})],
                        defenses="aucune")
    assert issues == [("chercher_projets", "executed"), ("lire_fichier", "error")]
    assert "open-cours/cours-git-debutant" in vus["chercher_projets"] and "non autorisé" in vus["lire_fichier"]


def test_un_depot_hors_liste_blanche_reste_refuse_sans_aucune_defense():
    issues, vus = jouer([("lister_commits", {"depot": "demo/prive"}), ("chercher_issues", {"requete": "x",
                                                                                          "depot": "demo/prive"})],
                        defenses="aucune")
    assert issues == [("lister_commits", "error"), ("chercher_issues", "error")]
    assert all("non autorisé" in v and "CANARI" not in v for v in vus.values())
