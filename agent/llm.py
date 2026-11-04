"""Fabrique de modèle : le fournisseur est choisi par configuration (jamais dans le code).

SYNAPSE_LLM="<fournisseur>:<modèle>"
  ollama:qwen3.5:4b   -> modèle local via Ollama (aucune clé nécessaire)
  openai:...  google_genai:...  anthropic:...  -> modèles d'API (paquet LangChain du fournisseur + clé dans .env)
"""
import os


def get_llm(spec: str | None = None):
    spec = spec or os.getenv("SYNAPSE_LLM")
    if not spec:
        raise RuntimeError("SYNAPSE_LLM n'est pas défini (format 'fournisseur:modèle'). Voir .env.example")

    fournisseur, _, modele = spec.partition(":")   # coupe au premier « : » seulement

    if fournisseur == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=modele,
            temperature=0,
            reasoning=False,                                   # coupe la phase de « réflexion » (trop lente sur CPU)
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),  # longueur de contexte
        )

    from langchain.chat_models import init_chat_model
    return init_chat_model(modele, model_provider=fournisseur, temperature=0)