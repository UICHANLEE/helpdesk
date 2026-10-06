from __future__ import annotations

import asyncio
import ipaddress
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import actions, diagnose, incidents, infra, knowledge, reports, stream, tools
from backend.reports import daily
from backend.storage import backup
from backend.storage.sqlite import init_db


async def maintenance() -> None:
    while True:
        for task in (backup.backup_now, daily.refresh_all):
            try:
                await asyncio.to_thread(task)
            except Exception:
                # The SQLite original stays intact; try the backup/export again next pass.
                pass
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("VERCEL"):
        raise RuntimeError("This application is configured for local use only")
    init_db()
    worker = asyncio.create_task(maintenance())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="RAFT Incident Agent", version="0.1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def local_only(request: Request, call_next):
    try:
        loopback = ipaddress.ip_address(request.client.host).is_loopback if request.client else False
    except ValueError:
        loopback = False
    if not loopback:
        return JSONResponse({"detail": "로컬 연결만 허용합니다."}, status_code=403)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])
for router in (diagnose.router, incidents.router, infra.router, stream.router, tools.router, actions.router, knowledge.router, reports.router):
    app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
