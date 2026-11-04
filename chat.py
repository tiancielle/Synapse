"""Chat en terminal avec l'agent Synapse.

    python chat.py                      -> modèle défini par SYNAPSE_LLM dans .env (ex. ollama:qwen3.5:4b)
    python chat.py --demo               -> modèle simulé, sans Ollama (pour tester l'interface)
    python chat.py --defenses aucune    -> sans aucune défense (pour voir la différence)
    python chat.py --defenses registre  -> confirmation humaine seule, sans nettoyage des résultats
    python chat.py --source google      -> VRAI Google Calendar en lecture seule (après python connect_google.py)

Commandes dans le chat :  /audit  (journal d'audit)   /quitter
"""
import argparse
import asyncio
import json
import sys
import tempfile
from datetime import date, timedelta      # ← modif 1 : timedelta ajouté
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from agent.fakes import NaiveVictimLLM
from agent.firewall import DefenseConfig, Firewall
from agent.graph import build_graph
from agent.llm import get_llm
from agent.tools import Toolbox

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "servers" / "calendar_server.py"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DATE_DEMO = date(2026, 10, 18)     # « aujourd'hui » dans le calendrier de test (un dimanche)

DEFENSES = {
    "toutes": DefenseConfig(),
    "aucune": DefenseConfig.baseline(),
    "registre": DefenseConfig(use_registry=True, require_confirmation=True, scan_results=False, hardened_prompt=False),
}


# ← modif 2 : nouvelle fonction de repères temporels
def reperes_dates(jour_ref):
    """Texte de repères (aujourd'hui, demain, jours à venir) pour éviter que le modèle calcule les dates lui-même."""
    def nom(d):
        return f"{JOURS[d.weekday()]} {d.isoformat()}"
    suivants = [jour_ref + timedelta(days=i) for i in range(1, 8)]
    return (f"{nom(jour_ref)} (aujourd'hui). Demain = {nom(suivants[0])}. Après-demain = {nom(suivants[1])}. "
            f"Jours à venir : " + ", ".join(nom(d) for d in suivants))


def court(texte, n=110):
    texte = " ".join(str(texte).split())
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def afficher(noeud, maj, fw, deja_vus):
    """Affiche en direct ce que fait chaque nœud du graphe."""
    maj = maj or {}
    if noeud == "plan":
        print(f"  [plan]      {court(maj.get('plan', ''), 200)}")
    elif noeud == "act":
        msg = maj["messages"][-1]
        for tc in getattr(msg, "tool_calls", None) or []:
            print(f"  [outil]     l'agent demande : {tc['name']} {json.dumps(tc['args'], ensure_ascii=False)}")
    elif noeud == "gate":
        for p in maj.get("pending", []):
            print(f"  [pare-feu]  {p['name']} -> {p['decision']} ({p['reason']})")
    elif noeud == "tools":
        for e in fw.audit[deja_vus[0]:]:
            etat = "exécuté" if e["outcome"] == "executed" else "BLOQUÉ"
            print(f"  [résultat]  {e['tool']} : {etat}")
            if e["findings"]:
                print(f"  [ALERTE]    injection détectée et retirée du résultat : {e['findings']}")
        deja_vus[0] = len(fw.audit)
        for m in maj.get("messages", []):
            if str(m.content).startswith('{"erreur"'):
                print(f"  [ERREUR]    l'outil {m.name} a échoué : {court(m.content, 220)}")
    elif noeud == "verify":
        if maj.get("verified"):
            print("  [vérif]     réponse validée")
        else:
            print("  [vérif]     réponse refusée par le vérificateur, nouvelle tentative")


async def demander_confirmation(payload):
    print(f"\n  >>> L'agent veut exécuter une action sensible : {payload['tool']} {json.dumps(payload['args'], ensure_ascii=False)}")
    rep = await asyncio.to_thread(input, "  >>> Autoriser ? [o/N] ")
    return rep.strip().lower() in ("o", "oui", "y", "yes")


async def tour(graph, demande, cfg, fw, deja_vus):
    entree = {"messages": [HumanMessage(demande)], "plan": "", "pending": [],
              "iterations": 0, "retries": 0, "verified": False}
    while True:
        interruption = None
        async for chunk in graph.astream(entree, cfg, stream_mode="updates"):
            for noeud, maj in chunk.items():
                if noeud == "__interrupt__":
                    interruption = maj[0].value
                else:
                    afficher(noeud, maj, fw, deja_vus)
        if interruption is None:
            break
        entree = Command(resume={"approved": await demander_confirmation(interruption)})

    etat = await graph.aget_state(cfg)
    finale = next((m for m in reversed(etat.values["messages"]) if isinstance(m, AIMessage) and not m.tool_calls), None)
    print("\nAgent >", finale.content if finale else "(pas de réponse : limite d'itérations atteinte)")


def afficher_audit(fw):
    if not fw.audit:
        print("  (journal vide : aucun outil exécuté ou bloqué)")
    for e in fw.audit:
        print(f"  {e['tool']:<26}{e['decision']:<9}{e['outcome']:<10}{e['reason']}  {e['findings'] or ''}")


async def main(args):
    load_dotenv(ROOT / ".env")
    if args.source == "google" and not (ROOT / "secrets" / "token_calendar.json").exists():
        print("Pas encore connecté à Google. Lance d'abord :  python connect_google.py")
        return
    llm = NaiveVictimLLM() if args.demo else get_llm()
    fw = Firewall(DEFENSES[args.defenses], audit_path=ROOT / "data" / "private" / "audit.jsonl")
    jour_ref = date.today() if args.source == "google" else DATE_DEMO
    aujourdhui = reperes_dates(jour_ref)      # ← modif 3 : repères complets pour le graphe
    # calendrier de test remis à zéro à chaque lancement (dossier temporaire)
    env = {"SYNAPSE_BACKEND": "google" if args.source == "google" else "fixture",
           "SYNAPSE_STATE_DIR": tempfile.mkdtemp(prefix="synapse_chat_")}

    async with Toolbox("calendar", SERVER, env=env, log_path=ROOT / "servers" / "calendar_server.log") as tb:
        graph = build_graph(tb, llm, fw, aujourdhui)
        cfg = {"configurable": {"thread_id": "chat"}}
        deja_vus = [0]
        print("=" * 70)
        print(f" Synapse | modèle : {'simulé (--demo)' if args.demo else 'défini par SYNAPSE_LLM'} | défenses : {args.defenses}")
        if args.source == "google":                                                    # ← modif 4 : en-tête allégé
            print(f" Date du jour : {jour_ref.isoformat()} | VRAI Google Calendar (lecture seule)")
        else:
            print(f" Date simulée : {jour_ref.isoformat()} | calendrier de test (données fictives)")
        print(" Commandes : /audit  /quitter")
        print("=" * 70)
        while True:
            try:
                texte = (await asyncio.to_thread(input, "\nVous > ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if texte in ("/quitter", "/q"):
                break
            if texte == "/audit":
                afficher_audit(fw)
            elif texte:
                await tour(graph, texte, cfg, fw, deja_vus)
    print("\nAu revoir. Journal d'audit enregistré dans data/private/audit.jsonl")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chat en terminal avec l'agent Synapse")
    parser.add_argument("--demo", action="store_true", help="modèle simulé (sans Ollama)")
    parser.add_argument("--defenses", choices=list(DEFENSES), default="toutes")
    parser.add_argument("--source", choices=["test", "google"], default="test",
                        help="test = données fictives ; google = vrai Google Calendar (lecture seule)")
    asyncio.run(main(parser.parse_args()))