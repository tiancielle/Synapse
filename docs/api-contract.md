# Contrat d'API Tandem / AgentFlow — version 1.5

Propriétaire : conversation backend et IA. Toute modification incrémente la version et est notifiée au frontend.
L'API écoute uniquement sur `127.0.0.1:8000`. CORS : `http://localhost:3000` et `http://127.0.0.1:3000`.

## Historique

| Version | Changement |
|---|---|
| 1.0 | Contrat initial (health, chat, confirm, audit, événements SSE) |
| 1.1 | `GET /api/health` : ajout du champ `llm` (additif) |
| 1.2 | Nouvel événement SSE `token` (streaming de la réponse finale, additif) |
| 1.3 | `outcome` peut valoir `"error"` (audit et `tool_result`) ; `tool_error` toujours émis une fois par échec |
| 1.4 | Champ `server` (serveur MCP d'origine de l'outil) dans les événements d'outils et dans l'audit (additif) |
| 1.5 | `GET /api/health` : ajout du champ `mail_source` (`test`|`gmail`, additif) |

## Endpoints

### `GET /api/health`
```json
{"status": "ok", "source": "test|google", "mail_source": "test|gmail",
 "defenses": "toutes|aucune|registre", "model": "demo|llm", "llm": "ollama:qwen3.5:4b"}
```
`llm` vaut `null` quand `model` = `"demo"`.
`mail_source` : provenance des mails (`test` = fixture ; `gmail` = vrai Gmail lecture seule).

### `POST /api/chat`
Corps : `{"session_id": "[A-Za-z0-9_-]{1,64}", "message": "1 à 2000 caractères"}`
Réponse : flux SSE (`text/event-stream`), une ligne `data: {json}` par événement.
- `409` : une confirmation est en attente pour cette session.
- `422` : requête invalide.

### `POST /api/confirm`
Corps : `{"session_id": "...", "approved": true|false}`
Réponse : flux SSE. `409` si aucune confirmation n'est en attente.

### `GET /api/audit`
`{"entries": [{"ts", "server", "tool", "args", "decision", "outcome", "reason", "findings"}]}`
`outcome` : `executed` (outil appelé avec succès), `blocked` (refusé par le pare-feu ou l'utilisateur), `error` (outil appelé mais en échec).
`server` : serveur MCP de l'outil (`calendar`, plus tard `mail`) ; `"inconnu"` si le nom d'outil demandé n'existe sur aucun serveur.

## Serveurs et noms d'outils

Le modèle voit les outils sous la forme `serveur__outil` (ex. `calendar__lister_evenements`). **Le frontend ne voit jamais le préfixe** :
`name` / `tool` contiennent le nom court (`lister_evenements`) et `server` le serveur (`calendar`).

## Événements SSE

| `type` | Champs | Sens |
|---|---|---|
| `plan` | `text` | Plan du planificateur |
| `tool_call` | `id`, `server`, `name`, `args` | L'agent demande un outil |
| `firewall` | `server`, `tool`, `decision` (`auto\|notify\|confirm\|deny`), `reason`, `approved` | Décision du pare-feu |
| `tool_result` | `server`, `tool`, `outcome` (`executed\|blocked\|error`) | Résultat de l'appel |
| `alert` | `server`, `tool`, `findings[]` | Injection détectée et retirée du résultat |
| `tool_error` | `server`, `tool`, `message` | L'outil a échoué (message générique) ; suit un `tool_result` d'`outcome` `error` |
| `token` | `text` | Morceau de la réponse de l'assistant (streaming) |
| `verify` | `ok` | Verdict du vérificateur |
| `confirmation_required` | `server`, `tool`, `args`, `reason` | Attente d'une validation humaine |
| `final` | `text` | Réponse finale (**référence**) |
| `error` | `message` | Erreur interne |
| `done` | `status` (`completed\|waiting_confirmation\|error`) | Fin du flux |

`server` est une chaîne (ex. `"calendar"`). Dans `tool_call`, il peut être `null` si le modèle a demandé un nom sans préfixe : l'appel sera alors refusé (`firewall` avec `server: "inconnu"`).
Chaque flux se termine par exactement un `done`.

### Règles pour `token`

- Les `token` s'accumulent dans la bulle de l'assistant, dans l'ordre d'arrivée.
- Le modèle découpe très fin (parfois un caractère par `token`) : regrouper l'affichage (une mise à jour par image) plutôt qu'un rendu par événement.
- `final.text` **remplace toujours** le texte accumulé : c'est la référence.
- Si un `tool_call` arrive après des `token`, ce texte était intermédiaire : l'effacer.
- Si `verify` vaut `ok: false`, effacer le texte accumulé : l'agent va réessayer et streamer à nouveau.
- Aucun `token` n'est envoyé en mode `demo` ni avec un modèle qui ne streame pas : le frontend retombe sur `final`.

## Résumé à transmettre au frontend (v1.5)

Dans `web/src/lib/types.ts`, ajouter `server?: string | null;` aux types `tool_call`, `firewall`, `tool_result`, `alert`, `tool_error` et `confirmation_required`, et à l'entrée d'audit. Aucun champ existant ne change : `name` et `tool` restent les noms courts.
Optionnel : afficher une pastille avec le serveur (« calendar », puis « mail »).
Rappels : v1.3 `tool_result.outcome` peut valoir `"error"` ; v1.2 événement `token` ; v1.1 `Health.llm: string | null`.

Dans `web/src/lib/types.ts`, ajouter `mail_source: "test" | "gmail"` au type Health (réponse de `GET /api/health`). Champ additif : les clients qui l'ignorent restent valides.
