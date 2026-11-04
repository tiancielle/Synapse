"""API FastAPI de Synapse (locale). Le navigateur ne voit jamais les clés ni le jeton Google.

POST /api/chat     {session_id, message}   -> flux d'événements (SSE)
POST /api/confirm  {session_id, approved}  -> reprend après une confirmation humaine (SSE)
GET  /api/audit                            -> journal d'audit
GET  /api/health                           -> état
"""
from __future__ import annotations

import json
import logging
import tempfile
from contextlib import asynccontextmanager
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.dates import DATE_DEMO, reperes_dates
from agent.fakes import NaiveVictimLLM
from agent.firewall import Firewall
from agent.graph import build_graph
from agent.llm import get_llm
from agent.tools import Toolbox
from api.service import AgentService
from api.settings import DEFENSE_PRESETS, ROOT, Settings

log = logging.getLogger("synapse.api")
SERVER = ROOT / "servers" / "calendar_server.py"
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv(ROOT / ".env")
        if settings.source == "google" and not (ROOT / "secrets" / "token_calendar.json").exists():
            raise RuntimeError("Pas encore connecté à Google. Lance d'abord :  python connect_google.py")
        llm = NaiveVictimLLM() if settings.demo else get_llm(settings.llm_spec)
        firewall = Firewall(DEFENSE_PRESETS[settings.defenses], audit_path=settings.audit_path)
        jour_ref = date.today() if settings.source == "google" else DATE_DEMO
        env = {"SYNAPSE_BACKEND": "google" if settings.source == "google" else "fixture",
               "SYNAPSE_STATE_DIR": tempfile.mkdtemp(prefix="synapse_api_")}
        async with Toolbox("calendar", SERVER, env=env, log_path=ROOT / "servers" / "calendar_server.log") as toolbox:
            graph = build_graph(toolbox, llm, firewall, reperes_dates(jour_ref))
            app.state.service = AgentService(graph, firewall)
            app.state.settings = settings
            yield

    app = FastAPI(title="Synapse API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.get("/api/health")
    async def health(request: Request):
        s: Settings = request.app.state.settings
        return {"status": "ok", "source": s.source, "defenses": s.defenses, "model": "demo" if s.demo else "llm"}

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