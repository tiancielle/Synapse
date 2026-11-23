"""Chat en terminal avec l'agent Tandem.

    python chat.py                      -> modèle défini par SYNAPSE_LLM dans .env (ex. ollama:qwen3.5:4b)
    python chat.py --demo               -> modèle simulé, sans Ollama (pour tester l'interface)
    python chat.py --defenses aucune    -> sans aucune défense (pour voir la différence)
    python chat.py --defenses registre  -> confirmation humaine seule, sans nettoyage des résultats
    python chat.py --source google      -> VRAI Google Calendar en lecture seule (après python connect_google.py)
    python chat.py --mail-source gmail  -> VRAI Gmail en lecture seule (après python connect_gmail.py)

Commandes dans le chat :  /audit  (journal d'audit)   /quitter
"""
import argparse
import asyncio
import json
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from agent.fakes import NaiveVictimLLM
from agent.llm import get_llm
from agent.runtime import (DEFENSE_PRESETS, ROOT, open_runtime, verifier_connexion_gmail,
                           verifier_connexion_google)

LIBELLES_ISSUE = {"executed": "exécuté", "blocked": "BLOQUÉ", "error": "ÉCHEC"}


def libelle_issue(outcome: str) -> str:
    return LIBELLES_ISSUE.get(outcome, outcome)


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
            print(f"  [résultat]  {e['tool']} : {libelle_issue(e['outcome'])}")
            if e["outcome"] == "error":
                print("  [ERREUR]    l'outil a échoué (cause dans servers/calendar_server.log)")
            if e["findings"]:
                print(f"  [ALERTE]    injection détectée et retirée du résultat : {e['findings']}")
        deja_vus[0] = len(fw.audit)
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
    try:
        verifier_connexion_google(args.source)
        verifier_connexion_gmail(args.mail_source)
    except RuntimeError as erreur:
        print(erreur)
        return
    llm = NaiveVictimLLM() if args.demo else get_llm()
    async with open_runtime(source=args.source, defenses=args.defenses, llm=llm,
                            mail_source=args.mail_source, state_prefix="synapse_chat_") as rt:
        cfg = {"configurable": {"thread_id": "chat"}}
        deja_vus = [0]
        print("=" * 70)
        print(f" Tandem | modèle : {'simulé (--demo)' if args.demo else 'défini par SYNAPSE_LLM'} | défenses : {args.defenses}")
        if args.source == "google":
            print(f" Date du jour : {rt.jour_ref.isoformat()} | VRAI Google Calendar (lecture seule)")
        else:
            print(f" Date simulée : {rt.jour_ref.isoformat()} | calendrier de test (données fictives)")
        print(f" Mail : {'VRAI Gmail (lecture seule)' if args.mail_source == 'gmail' else 'données de test (fixture)'}")
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
                afficher_audit(rt.firewall)
            elif texte:
                await tour(rt.graph, texte, cfg, rt.firewall, deja_vus)
    print("\nAu revoir. Journal d'audit enregistré dans data/private/audit.jsonl")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chat en terminal avec l'agent Tandem")
    parser.add_argument("--demo", action="store_true", help="modèle simulé (sans Ollama)")
    parser.add_argument("--defenses", choices=list(DEFENSE_PRESETS), default="toutes")
    parser.add_argument("--source", choices=["test", "google"], default="test",
                        help="test = données fictives ; google = vrai Google Calendar (lecture seule)")
    parser.add_argument("--mail-source", choices=["test", "gmail"], default="test",
                        help="test = mails fictifs ; gmail = vrai Gmail (lecture seule)")
    asyncio.run(main(parser.parse_args()))