from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import actions, diagnose, incidents, infra, knowledge, reports, stream, sync, tools
from backend.auth import cloud_ready, gate, router as auth_router
from backend.reports import daily
from backend.storage.sqlite import cloud_mode, init_db
from backend.storage import supabase


async def maintenance() -> None:
    while True:
        try:
            await asyncio.to_thread(daily.refresh_all)
            if supabase.configured():
                await asyncio.to_thread(supabase.flush)
        except Exception:
            # Local incident persistence remains authoritative; retry on the next pass.
            pass
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if cloud_ready():
        init_db()
    worker = None if cloud_mode() else asyncio.create_task(maintenance())
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass


app = FastAPI(title="RAFT Incident Agent", version="0.1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(gate)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])
for router in (auth_router, diagnose.router, incidents.router, infra.router, stream.router, tools.router, actions.router, knowledge.router, reports.router, sync.router):
    app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
