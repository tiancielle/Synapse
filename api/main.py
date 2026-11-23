"""API FastAPI de Tandem (locale). Le navigateur ne voit jamais les clés ni le jeton Google.

POST /api/chat     {session_id, message}   -> flux d'événements (SSE)
POST /api/confirm  {session_id, approved}  -> reprend après une confirmation humaine (SSE)
GET  /api/audit                            -> journal d'audit
GET  /api/health                           -> état
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.fakes import NaiveVictimLLM
from agent.llm import get_llm
from agent.runtime import open_runtime, verifier_connexion_gmail, verifier_connexion_google
from api.service import AgentService
from api.settings import ROOT, Settings

log = logging.getLogger("synapse.api")
SESSION_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_PATTERN)
    message: str = Field(min_length=1, max_length=2000)


class ConfirmRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_PATTERN)
    approved: bool


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream(service: AgentService, make_events) -> StreamingResponse:
    async def generate():
        try:
            async with service.lock:
                async for event in make_events():
                    yield _sse(event)
        except Exception:
            log.exception("Erreur pendant l'exécution de l'agent")
            yield _sse({"type": "error", "message": "Erreur interne de l'agent (voir les journaux du serveur)."})
            yield _sse({"type": "done", "status": "error"})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def create_app(settings: Settings | None = None, llm_factory=None) -> FastAPI:
    """`llm_factory(spec) -> modèle` : permet aux tests de fournir un modèle sans Ollama."""
    settings = settings or Settings.from_env()
    make_llm = llm_factory or get_llm

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv(ROOT / ".env")
        verifier_connexion_google(settings.source)
        verifier_connexion_gmail(settings.mail_source)
        llm = NaiveVictimLLM() if settings.demo else make_llm(settings.llm_spec)
        # nom du modèle annoncé au frontend (lu APRÈS load_dotenv) ; null en mode démo
        app.state.llm_name = None if settings.demo else (settings.llm_spec or os.getenv("SYNAPSE_LLM"))
        async with open_runtime(source=settings.source, defenses=settings.defenses, llm=llm,
                                mail_source=settings.mail_source,
                                audit_path=settings.audit_path, state_prefix="synapse_api_") as rt:
            app.state.service = AgentService(rt.graph, rt.firewall)
            app.state.settings = settings
            yield

    app = FastAPI(title="Tandem API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.get("/api/health")
    async def health(request: Request):
        s: Settings = request.app.state.settings
        return {"status": "ok", "source": s.source, "mail_source": s.mail_source,
                "defenses": s.defenses, "model": "demo" if s.demo else "llm",
                "llm": request.app.state.llm_name}

    @app.post("/api/chat")
    async def chat(req: ChatRequest, request: Request):
        service: AgentService = request.app.state.service
        if req.session_id in service.waiting:
            raise HTTPException(409, "Une confirmation est en attente pour cette session.")
        return _stream(service, lambda: service.run(req.session_id, req.message))

    @app.post("/api/confirm")
    async def confirm(req: ConfirmRequest, request: Request):
        service: AgentService = request.app.state.service
        if service.waiting.pop(req.session_id, None) is None:
            raise HTTPException(409, "Aucune confirmation en attente pour cette session.")
        return _stream(service, lambda: service.resume(req.session_id, req.approved))

    @app.get("/api/audit")
    async def audit(request: Request):
        return {"entries": request.app.state.service.fw.audit}

    return app