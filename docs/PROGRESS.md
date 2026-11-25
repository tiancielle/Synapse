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

- GH-4 (essai réel, 2026-11-25) : lister_depots, lister_pull_requests et lister_commits exécutés sur les vrais dépôts de l'étudiante, réponses justes ; dépôt hors liste blanche refusé. Bug trouvé et corrigé : sans le calendrier de test, la date de référence est la vraie date (avant : date fixe 2026-10-18).
- D6 (accepté par le gérant) : outil chercher_projets (GET /search/repositories, tout GitHub, FICHES seulement ; lecture toujours limitée à la liste blanche) ; fixture recherche_publique avec 1 attaque (vecteur repo_search) et 1 piège. Descriptions : github seul 2546 car. (specs 5861), trois serveurs 4075 (10357).
- D7 (accepté par le gérant) : SYNAPSE_GITHUB_REPOS facultatif. Vide = découverte au premier appel d'outil (GET /user/repos?affiliation=owner, tri par dernier push) : dépôts dont le compte du jeton est propriétaire, 50 au maximum (au-delà, refus), échec non mémorisé ; la liste découverte est la liste blanche (hors liste = refus avant requête) ; depot vide = agrégation sur les 10 plus récemment poussés ; lister_depots sans autre appel. Liste écrite dans .env prioritaire (10 max, évaluation inchangée). Le jeton (Only select / All repositories) borne l'accès.
- UI-1 (demandée par le gérant, faite dans cette conversation) : refonte de web/ en espace de travail. Coque (navigation, palette Ctrl+K, cloche des approbations, thème clair/sombre/système mémorisé sans flash), pages Vue d'ensemble, Studio, Conversations, Observatoire, Approbations, Explorateur MCP, Mail, Calendrier, GitHub, Réglages. Aucune route backend ajoutée : health, chat, confirm, audit + conversations du navigateur. Exécution partagée (lib/runner.ts) : une réponse continue d'une page à l'autre. Catalogue d'affichage web/src/lib/catalog.json vérifié contre le registre (tests/test_web_catalog.py). Type Health aligné sur le contrat v1.6. Tests frontend : npm test (node --test, 13 tests). Pas de « Automation Lab » (aucun moteur d'automatisation dans le backend).

## Reste à faire
- GH-4 : essai réel par l'étudiante (dépôt de test + 2-3 dépôts réels, jeton fine-grained lecture seule).
- EVAL-0 : docs/design-eval.md (document seulement) -> décisions E1-E5 du gérant.
- D3 : lister_dossier (reporté ; chercher_issues fait en GH-5).
- Refonte de l'interface : conversation frontend (web/).

## Dernier pytest
2026-11-25, UI-1 : suite complète 375 passed, 0 failed (durée affichée 16 h 44 : machine en veille pendant l'exécution, durée réelle non mesurée). Frontend : npm test 15 passed, tsc et eslint sans erreur, next build OK (11 routes statiques). Corrections de relecture appliquées après la suite (frontend seulement).
2026-11-25, D7 : suite ciblée (github, runtime, neutralité, exemples, agent) 210 passed (2 min 30) ; après corrections de relecture (page suivante, 50 exactement, refus sans liste de noms), tests GitHub 173 passed (25 s). Suite complète non relancée.
2026-11-25, D6 + correctif date : suite complète 361 passed (4 min 21) ; correction de relecture is:public appliquée ensuite, tests GitHub outils relancés : 55 passed.
GH-3bis : suite complète 300 passed (3 min 30). GH-5 : suite complète 349 passed (3 min 33) ; corrections de relecture (branche exige depot, sha hexadécimal) appliquées pendant cette exécution, puis tests GitHub relancés : 157 passed.
