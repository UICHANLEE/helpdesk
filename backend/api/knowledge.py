from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.knowledge import service
from backend.storage import sqlite as storage

router = APIRouter()


class FaqRequest(BaseModel):
    incident_id: str
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


@router.get("/knowledge")
def knowledge(query: str = Query(default="", max_length=500)) -> dict:
    return {"stats": service.stats(), "results": service.search(query) if query.strip() else [],
            "frequent_errors": service.frequent_errors(), "faq": storage.list_faq()}


@router.post("/knowledge/faq", status_code=201)
def publish_faq(request: FaqRequest) -> dict:
    incident = storage.get_incident(request.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    state = incident["state"]
    if state.get("origin") == "example":
        raise HTTPException(status_code=409, detail="예시 Incident는 실제 확인된 해결 기록이 아니므로 FAQ로 게시할 수 없습니다.")
    if state["status"] != "resolved" or not state.get("resolution"):
        raise HTTPException(status_code=409, detail="확인된 원인과 성공한 조치로 Incident를 해결 처리한 뒤 FAQ를 게시하세요.")
    domain = (state.get("classification") or {}).get("domain", "UNKNOWN")
    return storage.save_faq(service.signature(domain, state["resolution"]["rootCause"]), request.question, request.answer)


@router.get("/knowledge/faq-candidates")
def faq_candidates() -> list[dict]:
    return service.frequent_errors()
