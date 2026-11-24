# AgentFlow : consignes pour Claude Code

Mettre à jour docs/PROGRESS.md à chaque étape.

Commande de test (PowerShell) : `.\.venv\Scripts\python.exe -m pytest -q`   (Mac : `./.venv/bin/python -m pytest -q`).

# RÈGLES NON NÉGOCIABLES

1. Paliers de sécurité, jamais en sauter un : 0 données de test -> 1 compte réel en LECTURE SEULE -> 2 écriture avec confirmation -> 3 validé par l'évaluation -> 4 envoi/suppression/exécution réels avec confirmation. On est au palier 0, et au palier 1 pour le calendrier Google et le Gmail de test. Aucun outil d'écriture sur un vrai compte.
2. Moindre privilège : scopes minimaux, UN jeton par service, jetons à portée minimale. Refus par défaut (un outil non enregistré dans core/registry.py est refusé). Confirmation humaine pour l'irréversible.
3. Aucun secret dans Git ni dans tes messages. N'ouvre, n'affiche et ne copie JAMAIS secrets/, .env, credentials.json, token_*.json. Les tests ne dépendent d'aucun secret ni d'aucun réseau. Aucune donnée personnelle réelle dans le dépôt ni dans les tests (adresses de test en .test). Le contenu de vrais mails/issues ne va jamais dans le dépôt ni dans les rapports.
4. API locale uniquement (127.0.0.1).
5. L'injection de prompt est un problème NON résolu : n'écris jamais « sécurisé » ; mesure et borne le risque.
6. NEUTRALITÉ DE L'ABLATION : les descriptions d'outils et les prompts de base ne contiennent AUCUNE consigne de sécurité (« contenu non fiable », « n'obéis pas »...). Seule hardened_prompt peut en ajouter. Sinon le niveau « aucune défense » est faussé. Un test (tests/test_neutrality.py) le vérifie ; tout nouveau serveur doit y être ajouté.
7. SDK mcp VERSION 2 : classe MCPServer (from mcp.server.mcpserver import MCPServer), mcp_types.ToolAnnotations, client mcp.client.Client. PAS FastMCP, PAS les anciens exemples en ligne. Les erreurs ATTENDUES d'un outil se lèvent avec ToolError (from mcp.server.mcpserver.exceptions import ToolError) : son message arrive au modèle ; toute autre exception est réduite à « Error executing tool » (voir _ou_erreur_lisible dans servers/mail_server.py). Un message d'erreur ne contient JAMAIS de contenu de mail/issue/fichier.
8. Vérifie les API (LangGraph 1.2.x, langchain 1.x, mcp 2.3, FastAPI, google-api-python-client) dans le code INSTALLÉ ou la documentation, jamais de mémoire. Pour cela, utilise le sous-agent api-verifier.
9. Compatibilité Windows ET Mac : pathlib, pas de commande propre à un système hors d'une abstraction testée. PowerShell 5 déforme les guillemets de curl : fichier JSON + --data-binary. Pas de uvicorn --reload sous Windows.
10. Git : l'étudiant gère Git. Tu n'exécutes JAMAIS git add, commit, push, reset, checkout, restore, stash, rebase, clean. Tu peux lancer git status, git diff, git log, git ls-files, git check-ignore (lecture seule). À la fin de chaque étape tu donnes les commandes de commit à l'étudiant. Ne propose jamais de « revenir en arrière » sur des fichiers sans le dire explicitement (un retour en arrière silencieux a déjà annulé du travail validé).
11. Le contrat d'API (docs/api-contract.md, version 1.5) ne change que sur décision du gérant : tout nouveau champ est une DÉCISION à soumettre dans ton rapport, avec un résumé prêt à transmettre à la conversation frontend.
12. Un changement à la fois, tests verts avant de continuer, chaque comportement nouveau a ses tests. Aucune fonctionnalité décorative, aucun refactoring non demandé. Le calendrier est GELÉ (la professeure le trouve faible) : ne l'améliore pas.
13. Commande de test (PowerShell) : .\.venv\Scripts\python.exe -m pytest -q   (Mac : ./.venv/bin/python -m pytest -q).
