# Contrat d'API Tandem / AgentFlow — version 1.6

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
| 1.6 | `GET /api/health` : ajout des champs `github_source` (`test`|`github`) et `servers` (serveurs MCP lancés), additifs |

## Endpoints

### `GET /api/health`
```json
{"status": "ok", "source": "test|google", "mail_source": "test|gmail", "github_source": "test|github",
 "servers": ["calendar", "mail", "github"],
 "defenses": "toutes|aucune|registre", "model": "demo|llm", "llm": "ollama:qwen3.5:4b"}
```
`llm` vaut `null` quand `model` = `"demo"`.
`mail_source` : provenance des mails (`test` = fixture ; `gmail` = vrai Gmail lecture seule).
`github_source` : provenance des dépôts (`test` = fixture ; `github` = vrai GitHub lecture seule, dépôts de la liste blanche).
`servers` : serveurs MCP réellement lancés, dans l'ordre `calendar`, `mail`, `github` (sous-ensemble non vide,
choisi par `--servers` / `SYNAPSE_SERVERS`). `source`, `mail_source` et `github_source` sont TOUJOURS présents
(valeur de configuration), même si le serveur correspondant n'est pas lancé : le frontend doit se fier à `servers`.

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
`server` : serveur MCP de l'outil (`calendar`, `mail`, `github`) ; `"inconnu"` si le nom d'outil demandé n'existe sur aucun serveur.

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

## Résumé à transmettre au frontend (v1.6, récapitule tous les ajouts depuis la v1.0)

Tous les changements sont **additifs** : un client v1.0 qui ignore les nouveaux champs reste valide. Aucun champ existant n'a changé de sens.

1. **Type `Health`** (`GET /api/health`), dans `web/src/lib/types.ts` :
   ```ts
   type Health = {
     status: "ok";
     source: "test" | "google";
     defenses: "toutes" | "aucune" | "registre";
     model: "demo" | "llm";
     llm: string | null;                         // v1.1 : nom du modèle, null en mode démo
     mail_source: "test" | "gmail";              // v1.5
     github_source: "test" | "github";           // v1.6
     servers: ("calendar" | "mail" | "github")[]; // v1.6 : serveurs lancés, ordre fixe, jamais vide
   };
   ```
   Suggestion d'affichage : une pastille par serveur de `servers`, avec « test » ou « réel » selon la source correspondante (`source` pour calendar, `mail_source` pour mail, `github_source` pour github). Ne pas afficher une source dont le serveur n'est pas lancé.
2. **Événement SSE `token`** (v1.2) : `{type: "token", text}`, morceaux de la réponse ; règles dans la section « Règles pour `token` » ci-dessus (`final.text` reste la référence).
3. **`outcome: "error"`** (v1.3) : `tool_result.outcome` et l'entrée d'audit valent `"executed" | "blocked" | "error"` ; un `tool_error` (`server`, `tool`, `message`) est émis une fois par échec.
4. **Champ `server`** (v1.4) : `server?: string | null` sur `tool_call`, `firewall`, `tool_result`, `alert`, `tool_error`, `confirmation_required` et l'entrée d'audit. Valeurs : `"calendar"`, `"mail"`, `"github"`, ou `"inconnu"` (nom d'outil inexistant ; `null` possible dans `tool_call`). `name` / `tool` restent les noms courts, sans préfixe.
