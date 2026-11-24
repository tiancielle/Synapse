# Avancement AgentFlow

## Étape en cours
GH-3 terminée (serveur GitHub intégré au runtime, --github-source test|github). En attente de « OK étape suivante » pour GH-4 (essai réel avec l'étudiant).

## Fait
- Étape 0 : vérification ; nouveau serveur mail remis à sa place (il était dans servers/hello_server.py).
- Étape 1 : CLAUDE.md, .claude/agents/{test-runner,api-verifier,security-reviewer}.md, .claude/settings.json.
- Étape 2 : mcp 2.3.0 vérifié (ToolError transmis avec préfixe). Corrigé : limite_atteinte Gmail, années 2000-2100, données de test fictives.
- GH-1 : serveur github (5 outils READ), backend fixture, liste blanche serveur, data/fixtures/github.json (12/8/4). Détecteur : 2/8 attaques, 4/4 pièges, 0/12 normaux.
- GH-2 : GithubBackend (httpx, GET uniquement, follow_redirects=False, X-GitHub-Api-Version 2026-03-10), jeton SYNAPSE_GITHUB_TOKEN ou secrets/github_token lu au 1er appel, SYNAPSE_GITHUB_REPOS obligatoire pour le backend github. ErreurOutil = seule exception transmise au modèle ; réponses mal formées -> message fixe ; numero borné 1..1e9 ; journal httpx en WARNING.
- GH-3 : serveur github dans runtime.serveurs_par_defaut (fixture par défaut) ; --github-source test|github (chat.py, run_api.py) et SYNAPSE_GITHUB_SOURCE (API) ; cohérence stricte du registre pour github ; vérification au démarrage (liste blanche + fichier secrets/github_token). Le SDK mcp ne transmet pas os.environ au serveur (mcp/client/stdio.py:129) : la liste blanche est passée explicitement, le jeton jamais (fichier uniquement en passant par le runtime).

## Reste à faire
- GH-4 : essai réel avec l'étudiant (jeton fine-grained lecture seule sur UN dépôt de test).
- Décision gérant : champ github_source dans /api/health (proposé, non implémenté).
- Décision gérant en attente (étape 2) : nettoyer `requete` des opérateurs Gmail.
- Décision gérant (après GH-4) : outils lister_dossier / chercher_issues (lecture seule).
- Refonte de l'interface : conversation frontend (web/).

## Dernier pytest
2026-11-24 : suite complète 282 passed en 2 min 38 (étudiant, après GH-2). GH-3 : tests ciblés runtime/multiserver/github_agent/api 40 passed.
