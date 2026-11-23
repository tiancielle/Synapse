import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from agent.fakes import StreamingFakeLLM
from api.events import translate_message_chunk
from api.main import create_app
from api.settings import Settings

HOSTS = ("testserver", "localhost", "127.0.0.1")
REPONSE = "Voici votre semaine en direct"


def parse_sse(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


# --- fonction pure : quels morceaux deviennent un événement token ---------------------------

def test_text_chunk_from_act_becomes_a_token():
    assert translate_message_chunk(AIMessageChunk(content="Bonjour"), {"langgraph_node": "act"}) == \
        {"type": "token", "text": "Bonjour"}


def test_chunks_from_other_nodes_are_ignored():
    for node in ("plan", "verify", None):
        assert translate_message_chunk(AIMessageChunk(content="OK"), {"langgraph_node": node}) is None
    assert translate_message_chunk(AIMessageChunk(content="OK"), None) is None


def test_tool_call_chunks_are_ignored():
    chunk = AIMessageChunk(content="", tool_call_chunks=[{"name": "lister_evenements", "args": "{}", "id": "1", "index": 0}])
    assert translate_message_chunk(chunk, {"langgraph_node": "act"}) is None


def test_complete_non_streamed_message_is_ignored():
    assert translate_message_chunk(AIMessage(content="Réponse complète"), {"langgraph_node": "act"}) is None


def test_empty_text_is_ignored():
    assert translate_message_chunk(AIMessageChunk(content=""), {"langgraph_node": "act"}) is None


def test_block_content_keeps_only_text_blocks():
    chunk = AIMessageChunk(content=[{"type": "text", "text": "Salut"}, {"type": "reasoning", "text": "secret"}])
    assert translate_message_chunk(chunk, {"langgraph_node": "act"}) == {"type": "token", "text": "Salut"}


# --- de bout en bout, avec un modèle qui streame -----------------------------------------------

def _streaming_client():
    settings = Settings(source="test", defenses="toutes", demo=False, llm_spec="fake:streaming",
                        audit_path=None, allowed_hosts=HOSTS)
    # un nouveau modèle par application : plan, puis réponse finale, puis verdict du vérificateur
    factory = lambda spec: StreamingFakeLLM(messages=iter([AIMessage(content="1. Répondre."),
                                                           AIMessage(content=REPONSE), AIMessage(content="OK")]))
    return TestClient(create_app(settings, llm_factory=factory))


def test_tokens_arrive_before_final_and_only_carry_the_answer():
    with _streaming_client() as client:
        events = parse_sse(client.post("/api/chat", json={"session_id": "st1", "message": "Bonjour"}))
    kinds = [e["type"] for e in events]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert len(tokens) > 1                                          # vraiment en morceaux
    assert "".join(tokens) == REPONSE                               # ni le plan ni le « OK » du vérificateur
    assert max(i for i, k in enumerate(kinds) if k == "token") < kinds.index("final")
    assert next(e for e in events if e["type"] == "final")["text"] == REPONSE   # final reste la référence
    assert events[-1] == {"type": "done", "status": "completed"}


def test_demo_mode_sends_no_token_and_still_ends_with_final():
    settings = Settings(source="test", defenses="toutes", demo=True, audit_path=None, allowed_hosts=HOSTS)
    with TestClient(create_app(settings)) as client:
        events = parse_sse(client.post("/api/chat", json={"session_id": "st2", "message": "Prépare ma semaine"}))
    kinds = [e["type"] for e in events]
    assert "token" not in kinds
    assert "final" in kinds