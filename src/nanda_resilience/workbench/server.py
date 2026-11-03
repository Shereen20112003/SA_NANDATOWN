from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .azure import AzureClient, ProviderError
from .config import load_deployments
from .coco import CocoClient
from .flows import evaluation, research
from .network import LiveNetwork
from .schemas import Draft, ResourceControl, RunRequest
from .sources import ALLOWED_HOSTS, SourceError, validate_url
from .store import Store

logger = logging.getLogger(__name__)
TERMINAL = {"complete", "failed", "cancelled", "interrupted"}


def create_app(env_file: Path | None = None, state_dir: Path | None = None,
               transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    env_file = env_file or Path.cwd() / ".env"
    state_dir = state_dir or Path.cwd() / ".workbench"
    store = Store(state_dir / "runs.sqlite3")
    tasks: dict[str, asyncio.Task] = {}
    disabled: set[str] = set()

    @asynccontextmanager
    async def lifespan(app):
        store.interrupt_stale()
        app.state.client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        yield
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*list(tasks.values()), return_exceptions=True)
        await app.state.client.aclose()

    app = FastAPI(title="Nanda Workbench", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.store = store

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin changes are not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    def config():
        return load_deployments(env_file)

    @app.get("/api/status")
    async def status():
        deployments, problems = config()
        resources = sorted({d.resource for d in deployments})
        return {
            "configured": bool(deployments) and not problems,
            "problems": problems,
            "deployments": [d.public() for d in deployments],
            "resources": [{"name": r, "disabled": r in disabled} for r in resources],
            "can_failover": len(resources) >= 2,
            "supported_hosts": list(ALLOWED_HOSTS),
            "max_model_calls": 12,
            "provider": deployments[0].provider if deployments else None,
            "runtime": "Nanda Town signed local messaging; Azure HTTPS or coco CLI / Copilot",
        }

    @app.post("/api/resources")
    async def control(body: ResourceControl):
        deployments, _ = config()
        if body.resource not in {d.resource for d in deployments}:
            raise HTTPException(404, "Unknown configured resource.")
        if body.disabled:
            disabled.add(body.resource)
        else:
            disabled.discard(body.resource)
        for run_id, task in tasks.items():
            if not task.done():
                store.emit(run_id, "fault", {"resource": body.resource, "disabled": body.disabled,
                                           "scope": "new calls only; in-flight calls continue"})
        return {"resource": body.resource, "disabled": body.disabled}

    def unexpected_done(run_id, task):
        tasks.pop(run_id, None)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("Run %s failed unexpectedly: %s", run_id, type(error).__name__)
            store.update(run_id, "failed", error="Unexpected application error. Check server logs.")

    async def execute(run_id, body, deployments):
        client = (CocoClient(state_dir / "coco-runtime") if deployments[0].provider == "coco"
                  else AzureClient(app.state.client))
        network = LiveNetwork(
            deployments, client, body.policy,
            lambda kind, data: store.emit(run_id, kind, data), disabled)
        store.update(run_id, "running")
        started = time.monotonic()
        try:
            try:
                result = (await research(body, network, app.state.client) if body.mode == "research"
                          else await evaluation(body, network))
            except* (ProviderError, SourceError) as group:
                # TaskGroup preserves individual reader failures; do not turn them into a brief.
                messages = []
                def collect(error):
                    if isinstance(error, BaseExceptionGroup):
                        for item in error.exceptions:
                            collect(item)
                    else:
                        messages.append(str(error))
                collect(group)
                raise ProviderError("; ".join(messages)) from group
            result.update(network.evidence())
            result["seconds"] = round(time.monotonic() - started, 2)
            store.update(run_id, "complete", result)
        except (ProviderError, SourceError) as exc:
            store.update(run_id, "failed", {"partial": network.evidence()}, str(exc))
        except asyncio.CancelledError:
            store.update(run_id, "cancelled", {"partial": network.evidence()},
                         "Cancelled. Already submitted cloud calls may still be billable or consume quota.")
            raise

    @app.post("/api/runs", status_code=202)
    async def start(body: RunRequest):
        deployments, problems = config()
        if not deployments or problems:
            raise HTTPException(503, "Configure Azure or coco in the local .env file first.")
        if len(tasks) >= 2:
            raise HTTPException(409, "Two runs are already active. Wait or cancel one.")
        if body.mode == "research":
            if not body.sources:
                raise HTTPException(422, "Add at least one public source.")
            try:
                for url in body.sources:
                    validate_url(url)
            except (SourceError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
        elif len(body.rubric.strip()) < 12:
            raise HTTPException(422, "Add a concrete evaluation rubric.")
        run_id = store.create(body.model_dump())
        task = asyncio.create_task(execute(run_id, body, deployments))
        tasks[run_id] = task
        task.add_done_callback(lambda completed: unexpected_done(run_id, completed))
        return {"id": run_id}

    @app.get("/api/runs")
    async def history():
        return store.list()

    def require_run(run_id):
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found.")
        return run

    @app.get("/api/runs/{run_id}")
    async def run(run_id: str):
        return require_run(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        require_run(run_id)
        task = tasks.get(run_id)
        if task is None or task.done():
            raise HTTPException(409, "This run is no longer active.")
        task.cancel()
        return {"requested": True}

    @app.post("/api/runs/{run_id}/draft")
    async def draft(run_id: str, body: Draft):
        record = require_run(run_id)
        if record["status"] != "complete" or record["request"]["mode"] != "research":
            raise HTTPException(409, "Only completed research briefs can be edited.")
        store.save_draft(run_id, body.text)
        return {"saved": True}

    @app.get("/api/runs/{run_id}/export")
    async def export(run_id: str):
        record = require_run(run_id)
        all_events, after = [], 0
        while batch := store.events(run_id, after):
            all_events.extend(batch)
            after = batch[-1]["seq"]
        return JSONResponse(
            {**record, "events": all_events},
            headers={"Content-Disposition": f'attachment; filename="nanda-run-{run_id}.json"'},
        )

    @app.get("/api/runs/{run_id}/events")
    async def stream(run_id: str, request: Request):
        require_run(run_id)
        try:
            after = max(0, int(request.headers.get("last-event-id", "0")))
        except ValueError as exc:
            raise HTTPException(400, "Invalid event cursor.") from exc

        async def events():
            nonlocal after
            while not await request.is_disconnected():
                batch = store.events(run_id, after)
                for event in batch:
                    after = event["seq"]
                    yield f"id: {after}\ndata: {json.dumps(event)}\n\n"
                if require_run(run_id)["status"] in TERMINAL and len(batch) < 250:
                    yield "event: finished\ndata: {}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.35)
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(static / "index.html")

    return app


def main():
    parser = argparse.ArgumentParser(description="Local, real-agent Nanda Workbench")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--state-dir", type=Path, default=Path(".workbench"))
    args = parser.parse_args()
    uvicorn.run(create_app(args.env_file.resolve(), args.state_dir.resolve()),
                host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
