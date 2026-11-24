# Avancement AgentFlow

## Étape en cours
GH-2 terminée (backend GitHub réel en lecture seule, testé sans réseau). En attente de « OK étape suivante » pour GH-3.

## Fait
- Étape 0 : vérification ; nouveau serveur mail remis à sa place (il était dans servers/hello_server.py).
- Étape 1 : CLAUDE.md, .claude/agents/{test-runner,api-verifier,security-reviewer}.md, .claude/settings.json.
- Étape 2 : mcp 2.3.0 vérifié (ToolError transmis avec préfixe). Corrigé : limite_atteinte Gmail, années 2000-2100, données de test fictives.
- GH-1 : serveur github (5 outils READ), backend fixture, liste blanche serveur, data/fixtures/github.json (12/8/4). Détecteur : 2/8 attaques, 4/4 pièges, 0/12 normaux.
- GH-2 : GithubBackend (httpx, GET uniquement, follow_redirects=False, X-GitHub-Api-Version 2026-03-10), jeton SYNAPSE_GITHUB_TOKEN ou secrets/github_token lu au 1er appel, SYNAPSE_GITHUB_REPOS obligatoire pour le backend github. ErreurOutil = seule exception transmise au modèle ; réponses mal formées -> message fixe ; numero borné 1..1e9 ; journal httpx en WARNING.

## Reste à faire
- GH-3 : runtime.serveurs_par_defaut + --github-source test|github (run_api.py, chat.py) + cohérence du registre au démarrage ; proposer github_source dans /api/health (décision gérant) ; instructions jeton pour l'étudiant.
- Décision gérant en attente (étape 2) : nettoyer `requete` des opérateurs Gmail.
- Refonte de l'interface : conversation frontend (web/).

## Dernier pytest
2026-11-24/25 : suite complète 269 passed (durée affichée 12 h 26, machine probablement en veille) ; après les corrections de relecture : tests GitHub ciblés 107 + 8 passed.
