"""Shared access code gate for every incident, knowledge and export API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

COOKIE = "helpdesk_session"
TTL = 12 * 60 * 60
_session_secret = os.getenv("ACCESS_SESSION_SECRET") or secrets.token_urlsafe(48)
_attempts: dict[str, deque[float]] = defaultdict(deque)
router = APIRouter()


class LoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


def _configured_code() -> str:
    return os.getenv("ACCESS_CODE", "helpdesk")


def cloud_ready() -> bool:
    if not os.getenv("VERCEL"):
        return True
    from backend.storage.supabase import configured
    return bool(os.getenv("ACCESS_SESSION_SECRET")) and configured()


def _sign(expires: int, nonce: str) -> str:
    payload = f"{expires}.{nonce}"
    signature = hmac.new(_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def authenticated(request: Request) -> bool:
    cookie = request.cookies.get(COOKIE, "")
    parts = cookie.split(".")
    if len(parts) != 3:
        return False
    try:
        expires = int(parts[0])
    except ValueError:
        return False
    if expires <= time.time() or expires > time.time() + TTL:
        return False
    expected = _sign(expires, parts[1])
    return hmac.compare_digest(cookie, expected)


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    source = urlparse(origin)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return source.netloc == host and source.scheme in ("http", "https")


async def gate(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/v1/auth/"):
        if not cloud_ready():
            return JSONResponse({"detail": "서버 저장소 연결이 준비되지 않았습니다."}, status_code=503,
                                headers={"Cache-Control": "no-store"})
        if not authenticated(request):
            return JSONResponse({"detail": "인증번호가 필요합니다."}, status_code=401, headers={"Cache-Control": "no-store"})
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
            return JSONResponse({"detail": "요청 출처가 일치하지 않습니다."}, status_code=403)
    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/status")
def status(request: Request) -> dict:
    ready = cloud_ready()
    return {"authenticated": ready and authenticated(request), "ready": ready}


@router.post("/auth/login")
def login(body: LoginRequest, request: Request) -> JSONResponse:
    if not cloud_ready():
        raise HTTPException(status_code=503, detail="서버 저장소 연결이 준비되지 않았습니다. 관리자에게 문의하세요.")
    address = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _attempts[address]
    while attempts and attempts[0] < now - 600:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="잠시 후 다시 시도하세요.")
    if not hmac.compare_digest(body.code, _configured_code()):
        attempts.append(now)
        raise HTTPException(status_code=401, detail="인증번호가 올바르지 않습니다.")
    attempts.clear()
    response = JSONResponse({"authenticated": True})
    response.set_cookie(COOKIE, _sign(int(time.time()) + TTL, secrets.token_hex(12)), max_age=TTL,
                        httponly=True, secure=os.getenv("VERCEL") == "1" or request.url.scheme == "https",
                        samesite="strict", path="/")
    return response


@router.post("/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE, path="/")
    return response
