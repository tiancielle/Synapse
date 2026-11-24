# Avancement AgentFlow

## Étape en cours
Mode accéléré (soutenance dans ~7 jours) : GH-3bis et GH-5 terminées ; GH-4 = procédure docs/essai-github.md, essai réel par l'étudiante (en attente de ses retours) ; EVAL-0 = docs/design-eval.md (décisions E1-E5 du gérant). Hors périmètre avant la soutenance : PowerShell, RAG.

## Fait
- Étape 0 : vérification ; nouveau serveur mail remis à sa place (il était dans servers/hello_server.py).
- Étape 1 : CLAUDE.md, .claude/agents/{test-runner,api-verifier,security-reviewer}.md, .claude/settings.json.
- Étape 2 : mcp 2.3.0 vérifié (ToolError transmis avec préfixe). Corrigé : limite_atteinte Gmail, années 2000-2100, données de test fictives.
- GH-1 : serveur github (5 outils READ), backend fixture, liste blanche serveur, data/fixtures/github.json (12/8/4). Détecteur : 2/8 attaques, 4/4 pièges, 0/12 normaux.
- GH-2 : GithubBackend (httpx, GET uniquement, follow_redirects=False, X-GitHub-Api-Version 2026-03-10), jeton SYNAPSE_GITHUB_TOKEN ou secrets/github_token lu au 1er appel, SYNAPSE_GITHUB_REPOS obligatoire pour le backend github. ErreurOutil = seule exception transmise au modèle ; réponses mal formées -> message fixe ; numero borné 1..1e9 ; journal httpx en WARNING.
- GH-3 : serveur github dans runtime.serveurs_par_defaut (fixture par défaut) ; --github-source test|github (chat.py, run_api.py) et SYNAPSE_GITHUB_SOURCE (API) ; cohérence stricte du registre pour github ; vérification au démarrage (liste blanche + fichier secrets/github_token). Le SDK mcp ne transmet pas os.environ au serveur (mcp/client/stdio.py:129) : la liste blanche est passée explicitement, le jeton jamais (fichier uniquement en passant par le runtime).

- GH-3bis : délai du test de démarrage 60 -> 180 s ; contrat v1.6 (/api/health : github_source, servers ; résumé frontend complet v1.0 -> v1.6) ; --servers / SYNAPSE_SERVERS (calendar, mail, github ; défaut tous ; vide ou inconnu = erreur), open_runtime ne lance et ne vérifie que les serveurs demandés ; prompts de base : « accès {sources actives} » (build_graph(sources=...), défaut historique calendrier + mail), test de neutralité des prompts ; D2 : requete nettoyée comme expediteur/sujet avant Gmail.

- GH-5 : liste blanche jusqu'à 10 dépôts ; nouveaux outils READ lister_depots, lister_commits, lister_versions, chercher_issues ; depot facultatif (agrégation triée par date) + filtre auteur pour lister_issues / lister_pull_requests ; dates et nettoyage partagés avec le mail (mail_filters.lire_periode, mots_sans_operateurs) ; fixture : dépôt demo/projet-y + 3 attaques (commit, description, version) et 2 pièges. Descriptions : github seul 2319 car. (specs JSON 5288), trois serveurs 3848 (9784). Détecteur sur les nouveaux vecteurs : 0/3 attaques, 1/2 pièges.

## Reste à faire
- GH-4 : essai réel par l'étudiante (dépôt de test + 2-3 dépôts réels, jeton fine-grained lecture seule).
- EVAL-0 : docs/design-eval.md (document seulement) -> décisions E1-E5 du gérant.
- D3 : lister_dossier (reporté ; chercher_issues fait en GH-5).
- Refonte de l'interface : conversation frontend (web/).

## Dernier pytest
GH-3bis : suite complète 300 passed (3 min 30). GH-5 : suite complète 349 passed (3 min 33) ; corrections de relecture (branche exige depot, sha hexadécimal) appliquées pendant cette exécution, puis tests GitHub relancés : 157 passed.
