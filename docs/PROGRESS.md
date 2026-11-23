# Avancement AgentFlow

## Étape en cours
ÉTAPE 2 terminée (relecture sécurité de la recherche mail). En attente de « OK GitHub » pour GH-1.

## Fait
- Étape 0 : lecture et vérification. Correction d'une erreur de copie : le nouveau serveur mail était dans servers/hello_server.py ; déplacé dans servers/mail_server.py, hello_server.py remis à sa version commitée.
- Étape 1 : CLAUDE.md, .claude/agents/{test-runner,api-verifier,security-reviewer}.md, .claude/settings.json (deny Read secrets/.env/jetons ; deny git en écriture via Bash ET PowerShell). Vérifié : lecture de secrets/ refusée, `git stash list` refusé, test-runner fonctionne.
- Étape 2 : mcp 2.3.0 vérifié (ToolError -> message transmis avec préfixe « Error executing tool <nom>: » ; autre exception -> message générique). Corrigé : limite_atteinte Gmail (search_page renvoie il_en_reste lu sur la réponse brute), années bornées 2000-2100 (plus d'OSError/OverflowError), noms et adresses de test fictifs.

## Reste à faire
- Décision gérant en attente : nettoyer aussi `requete` des opérateurs Gmail (in:, label:, OR).
- Bloc GitHub (GH-1 à GH-4) : après « OK GitHub ».
- Refonte de l'interface : dans la conversation frontend (web/), pas ici.

## Dernier pytest
2026-11-23, suite complète : 169 passed in 125.63s.
