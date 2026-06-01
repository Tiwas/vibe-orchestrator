from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import Store
from .fake_agent import FakeAgentRuntime
from .model_suggester import suggest_models


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(os.environ.get("VIBE_ORCHESTRATOR_HOME", ".vibe"))
DEFAULT_DB_PATH = Path(os.environ.get("VIBE_ORCHESTRATOR_DB", DEFAULT_DATA_DIR / "orchestrator.sqlite"))
DEFAULT_EVENT_LOG_PATH = Path(
    os.environ.get("VIBE_ORCHESTRATOR_EVENTS", DEFAULT_DATA_DIR / "logs" / "events.jsonl")
)


class CreateJobRequest(BaseModel):
    work_package: str = Field(min_length=1)
    provider_family: str = "fake"
    model: str = ""
    priority: int = 50
    affected: list[str] = Field(default_factory=list)


class ModelSuggestionRequest(BaseModel):
    work_package: str = Field(min_length=1)
    provider_family: str = "auto"
    affected: list[str] = Field(default_factory=list)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1)


class ControlRequest(BaseModel):
    command: str = Field(min_length=1)


def build_store() -> Store:
    return Store(DEFAULT_DB_PATH, DEFAULT_EVENT_LOG_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = build_store()
    store.initialize()
    app.state.store = store
    app.state.fake_runtime = FakeAgentRuntime(store)
    store.append_event(
        job_id=None,
        source_type="orchestrator",
        source_id="local",
        event_type="orchestrator.started",
        payload={"db_path": str(DEFAULT_DB_PATH), "event_log_path": str(DEFAULT_EVENT_LOG_PATH)},
    )
    yield
    store.append_event(
        job_id=None,
        source_type="orchestrator",
        source_id="local",
        event_type="orchestrator.stopped",
        payload={},
    )


app = FastAPI(title="Vibe Orchestrator", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")


def store() -> Store:
    return app.state.store


def fake_runtime() -> FakeAgentRuntime:
    return app.state.fake_runtime


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (PACKAGE_ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "db_path": str(DEFAULT_DB_PATH),
        "event_log_path": str(DEFAULT_EVENT_LOG_PATH),
        "providers": [
            {"family": "fake", "status": "available", "models": ["fake"]},
            {"family": "codex", "status": "planned", "models": []},
            {"family": "claude", "status": "planned", "models": []},
        ],
    }


@app.get("/api/events")
def list_events(after: int = 0, limit: int = 200) -> dict[str, Any]:
    events = store().list_events(after=after, limit=limit)
    return {"events": events, "last_event_id": events[-1]["event_id"] if events else after}


@app.get("/api/jobs")
def list_jobs(limit: int = 100) -> dict[str, Any]:
    return {"jobs": store().list_jobs(limit=limit)}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    jobs = store().list_jobs(limit=100)
    agents = store().list_agents(limit=100)
    agents_by_job = {}
    for agent in agents:
        agents_by_job.setdefault(agent["job_id"], []).append(agent)

    current_work = [
        {**job, "agents": agents_by_job.get(job["job_id"], [])}
        for job in jobs
        if job["status"] in {"running", "paused"}
    ]
    priority_log = [
        {**job, "agents": agents_by_job.get(job["job_id"], [])}
        for job in jobs
    ]
    priority_log.sort(key=lambda item: (-item["priority"], item["created_at"]))
    return {"current_work": current_work, "priority_log": priority_log}


@app.post("/api/model-suggestions")
def model_suggestions(request: ModelSuggestionRequest) -> dict[str, Any]:
    return {
        "suggestions": suggest_models(
            work_package=request.work_package,
            provider_family=request.provider_family,
            affected=request.affected,
        )
    }


@app.post("/api/jobs")
async def create_job(request: CreateJobRequest) -> dict[str, Any]:
    model = request.model.strip()
    if not model:
        suggestions = suggest_models(
            work_package=request.work_package,
            provider_family=request.provider_family,
            affected=request.affected,
        )
        raise HTTPException(
            status_code=409,
            detail={"message": "model_choice_required", "suggestions": suggestions},
        )

    job = store().create_job(
        work_package=request.work_package,
        provider_family=request.provider_family,
        model=model,
        priority=request.priority,
        affected=request.affected,
    )
    agent = None
    if job["provider_family"] == "fake":
        agent = fake_runtime().start_job(job)
    else:
        store().append_event(
            job_id=job["job_id"],
            source_type="scheduler",
            source_id=None,
            event_type="job.waiting_for_adapter",
            payload={"provider_family": job["provider_family"], "model": job["model"]},
        )
    return {"job": job, "agent": agent}


@app.get("/api/agents")
def list_agents(limit: int = 100) -> dict[str, Any]:
    return {"agents": store().list_agents(limit=limit)}


@app.get("/api/agents/{agent_id}/messages")
def list_agent_messages(agent_id: str, limit: int = 200) -> dict[str, Any]:
    try:
        store().get_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    return {"messages": store().list_messages(agent_id, limit=limit)}


@app.post("/api/agents/{agent_id}/messages")
def send_agent_message(agent_id: str, request: MessageRequest) -> dict[str, Any]:
    try:
        agent = store().get_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    message = store().append_message(
        agent_id=agent_id,
        job_id=agent["job_id"],
        direction="user_to_agent",
        message_type="chat",
        payload={"text": request.text},
        ack_status="pending",
    )
    return {"message": message}


@app.post("/api/agents/{agent_id}/control")
async def control_agent(agent_id: str, request: ControlRequest) -> dict[str, Any]:
    try:
        result = await fake_runtime().control(agent_id, request.command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    return result


def main() -> None:
    host = os.environ.get("VIBE_ORCHESTRATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("VIBE_ORCHESTRATOR_PORT", "8765"))
    uvicorn.run("vibe_orchestrator.app:app", host=host, port=port)
