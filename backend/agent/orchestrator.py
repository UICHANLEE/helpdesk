from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

from incident import get_tool_config, quick_response, qwen_model, qwen_model_available

from backend.agent.jev import classify
from backend.knowledge.fallback import from_verified_history
from backend.llm.qwen import diagnose as qwen_diagnose
from backend.models import AgentAction, ClaimReference, Classification, Evidence, Hypothesis, IncidentState, IncidentStatus, RaftMatch, TraceClaim
from backend.raft.retriever import retrieve
from backend.storage import sqlite as storage
from backend.tools.registry import execute, tools_for

_conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
_tasks: set[asyncio.Task] = set()


def classification_from(judgment: dict[str, Any]) -> Classification:
    return Classification(domain=judgment["primary"], secondary=judgment.get("secondary"), severity=judgment["severity"], complexity=judgment["depth"], source=judgment["source"], confidence=judgment.get("confidence"))


async def publish(incident_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    event = storage.append_event(incident_id, event_type, data)
    async with _conditions[incident_id]:
        _conditions[incident_id].notify_all()
    return event


def span(incident_id: str, kind: str, name: str) -> dict[str, Any]:
    return {"trace_id": f"TR-{incident_id}", "span_id": uuid4().hex[:16],
            "parent_span_id": f"TR-{incident_id}", "kind": kind, "name": name,
            "started_at": datetime.now(timezone.utc).isoformat()}


async def stream(incident_id: str, after_id: int = 0) -> AsyncIterator[dict[str, Any] | None]:
    cursor = after_id
    while True:
        events = storage.get_events(incident_id, cursor)
        if events:
            for event in events:
                cursor = event["id"]
                yield event
            continue
        try:
            async with _conditions[incident_id]:
                await asyncio.wait_for(_conditions[incident_id].wait(), timeout=15)
        except asyncio.TimeoutError:
            yield None


async def start(message: str) -> tuple[str, Classification]:
    classify_started_at = datetime.now(timezone.utc).isoformat()
    classify_started = time.perf_counter()
    parsed, judgment = await classify(message)
    classify_duration_ms = round((time.perf_counter() - classify_started) * 1000)
    qwen_ready = await asyncio.to_thread(qwen_model_available) if judgment["depth"] != "SIMPLE" else False
    classification = classification_from(judgment)
    quick = quick_response(parsed, judgment)
    state = IncidentState(
        id="", status=IncidentStatus.investigating, severity=classification.severity,
        symptoms=parsed["signals"] or [message[:240]],
        unknowns=["실제 시스템 상태", "근본 원인"], classification=classification,
        diagnosis=quick["diagnosis"], immediateActions=quick["immediate_actions"],
        recommendedAction=quick["recommended_action"], currentStep="route",
        providerStatus={"jev": judgment["source"], "raft": "pending", "qwen": "pending" if qwen_ready else "skipped" if judgment["depth"] == "SIMPLE" else "unavailable"},
    )
    incident_id = storage.create_incident(message, state)
    state.traceId = f"TR-{incident_id}"
    storage.save_state(state)
    await publish(incident_id, "user", {"message": message, "trace_id": state.traceId})
    await publish(incident_id, "jev", {"classification": classification.model_dump(), "parsed": {k: v for k, v in parsed.items() if k != "text"},
        "trace": {**span(incident_id, "route", classification.source), "started_at": classify_started_at,
                  "ended_at": datetime.now(timezone.utc).isoformat(), "duration_ms": classify_duration_ms, "status": "ok"}})
    task = asyncio.create_task(investigate(incident_id, parsed, judgment))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return incident_id, classification


async def rehearse_example(incident_id: str) -> tuple[Classification, asyncio.Task]:
    """Submit an example question through the same Jev → RAFT → tools → Qwen flow as live work."""
    record = storage.get_incident(incident_id)
    if not record or record["state"].get("origin") != "example":
        raise ValueError("Example incident not found")
    state = IncidentState.model_validate(record["state"])
    if state.examplePhase not in ("seeded", "awaiting_review"):
        raise ValueError("Example is already investigating or reviewed")
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    situation = (state.exampleReference or {}).get("situation", "")
    submitted_message = f"{record['message']}\n상황: {situation}" if situation else record["message"]
    parsed, judgment = await classify(submitted_message)
    if judgment["depth"] == "SIMPLE":
        judgment = {**judgment, "depth": "MEDIUM"}  # Practice cases should exercise Qwen as well.
    duration_ms = round((time.perf_counter() - started) * 1000)
    ready = True  # A transient /api/tags timeout must not skip the practice model call.
    classification = classification_from(judgment)
    quick = quick_response(parsed, judgment)
    state.status = IncidentStatus.investigating
    state.examplePhase = "investigating"
    state.classification = classification
    state.severity = classification.severity
    state.symptoms = [state.exampleReference["situation"]] if state.exampleReference else parsed["signals"] or [record["message"][:240]]
    state.unknowns = ["실제 시스템 상태", "근본 원인"]
    state.diagnosis = quick["diagnosis"]
    state.immediateActions = quick["immediate_actions"]
    state.recommendedAction = quick["recommended_action"]
    state.currentStep = "route"
    state.providerStatus = {"jev": judgment["source"], "raft": "pending", "qwen": "pending" if ready else "unavailable"}
    state.resolution = None
    state.raftMatches = []
    state.confirmedFacts = []
    state.hypotheses = []
    state.claims = []
    state.firstDiagnosis = None
    state.firstActions = []
    storage.save_state(state)
    await publish(incident_id, "rehearsal_started", {"message": record["message"], "origin": "example"})
    await publish(incident_id, "user", {"message": submitted_message, "origin": "example", "trace_id": state.traceId})
    await publish(incident_id, "jev", {"classification": classification.model_dump(), "parsed": {k: v for k, v in parsed.items() if k != "text"},
        "trace": {**span(incident_id, "route", classification.source), "started_at": started_at,
                  "ended_at": datetime.now(timezone.utc).isoformat(), "duration_ms": duration_ms, "status": "ok"}})
    task = asyncio.create_task(investigate(incident_id, parsed, judgment))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return classification, task


async def investigate(incident_id: str, parsed: dict[str, Any], judgment: dict[str, Any]) -> None:
    record = storage.get_incident(incident_id)
    if not record:
        return
    state = IncidentState.model_validate(record["state"])
    try:
        state.currentStep = "retrieve"
        storage.save_state(state)
        retrieval_span = span(incident_id, "retrieval", "RAFT search")
        started = time.perf_counter()
        matches = await retrieve(parsed, judgment, incident_id)
        state.raftMatches = [RaftMatch.model_validate(item) for item in matches]
        state.providerStatus["raft"] = "connected" if os.getenv("RAFT_SEARCH_URL") else "local_history"
        storage.save_state(state)
        retrieval_event = await publish(incident_id, "retrieval", {"matches": [match.model_dump() for match in state.raftMatches], "status": state.providerStatus["raft"],
            "trace": {**retrieval_span, "ended_at": datetime.now(timezone.utc).isoformat(),
                      "duration_ms": round((time.perf_counter() - started) * 1000),
                      "status": "ok" if matches else "empty", "result_count": len(matches), "index_source": state.providerStatus["raft"]}})

        tools = tools_for(judgment)
        configured_tools = get_tool_config()
        results: list[dict[str, Any]] = []
        tool_events: list[dict[str, Any]] = []
        for tool in tools:
            tool_span = span(incident_id, "tool", tool)
            if tool in configured_tools:
                await publish(incident_id, "tool_started", {"tool": tool, "trace": tool_span})
            started = time.perf_counter()
            result = await execute(tool, parsed)
            duration_ms = round((time.perf_counter() - started) * 1000)
            results.append(result)
            evidence_status = "confirmed" if result["status"] == "ok" else "failed" if result["status"] == "error" else "unavailable"
            evidence = Evidence(id=f"E{len(results)}", source=tool, summary=str(result["summary"]), status=evidence_status, data=result.get("data") if isinstance(result.get("data"), dict) else None)
            if evidence.status == "confirmed":
                state.confirmedFacts.append(evidence)
            storage.save_state(state)
            tool_events.append(await publish(incident_id, "tool_result", {"tool": tool, "result": result, "evidence": evidence.model_dump(),
                "trace": {**tool_span, "ended_at": datetime.now(timezone.utc).isoformat(),
                          "duration_ms": duration_ms, "status": result["status"]}}))

        state.currentStep = "reason"
        storage.save_state(state)
        context = quick_response(parsed, judgment)
        context["tool_results"] = results
        context["related_incidents"] = matches
        if state.origin == "example":
            context["practice"] = True
        llm_span = span(incident_id, "llm", qwen_model())
        if state.providerStatus.get("qwen") == "pending":
            await publish(incident_id, "reasoning_started", {"model": llm_span["name"], "complexity": judgment["depth"], "trace": llm_span})
        started = time.perf_counter()
        answer = await qwen_diagnose(parsed, judgment, context)
        llm_duration_ms = round((time.perf_counter() - started) * 1000)
        history_fallback = from_verified_history(matches) if answer is None else None
        final = answer or ({**context, **history_fallback} if history_fallback else context)
        state.providerStatus["qwen"] = "connected" if answer else "skipped" if judgment["depth"] == "SIMPLE" else "unavailable"
        if history_fallback:
            state.providerStatus["answer_source"] = "verified_history_check"
        if not answer and context.get("qwen_error"):
            state.providerStatus["qwen_error"] = context["qwen_error"]
        state.diagnosis = str(final.get("diagnosis") or context["diagnosis"])
        state.immediateActions = [str(item) for item in final.get("immediate_actions", [])][:6] or context["immediate_actions"]
        if state.origin == "example":
            state.firstDiagnosis = state.diagnosis
            state.firstActions = list(state.immediateActions)
            state.examplePhase = "awaiting_review"
        state.recommendedAction = str(final.get("recommended_action") or state.immediateActions[0])
        state.hypotheses = [Hypothesis(id=f"H{i+1}", name=str(item.get("name", "확인 필요")), confidence=item.get("confidence") if isinstance(item.get("confidence"), (int, float)) else None, rationale=str(item.get("rationale", ""))) for i, item in enumerate(final.get("hypotheses", [])) if isinstance(item, dict)]
        state.reasoningTrace = [
            {"step": "OBSERVATION", "text": "; ".join(state.symptoms)},
            {"step": "INTERPRETATION", "text": state.classification.domain if state.classification else "UNKNOWN"},
            {"step": "EVIDENCE", "text": "; ".join(item.summary for item in state.confirmedFacts) or
             (f"과거 해결 기록 {history_fallback['historical_case_id']} 참고 (현재 건 검증 전)" if history_fallback else "연결된 도구의 확인 결과 없음")},
            {"step": "HYPOTHESIS", "text": state.diagnosis},
            {"step": "NEXT TEST", "text": state.recommendedAction},
        ]
        state.actions = [AgentAction(id=f"{incident_id}-A1", label=state.recommendedAction, requires_approval=bool(final.get("requires_approval", False)))]
        state.status = IncidentStatus.action_required
        state.currentStep = "act"
        user_event = next((event for event in reversed(storage.get_events(incident_id)) if event["type"] == "user"), None)
        references = [ClaimReference(eventId=user_event["id"], relation="reported")] if user_event else []
        if any(match.get("verification") == "verified" for match in matches):
            references.append(ClaimReference(eventId=retrieval_event["id"], relation="historical_match"))
        references.extend(ClaimReference(eventId=event["id"], relation="observed" if event["data"]["result"]["status"] == "ok" else "failed_check")
                          for event in tool_events if event["data"]["result"]["status"] != "unconfigured")
        state.claims = [TraceClaim(id=f"{incident_id}-C1", text=state.diagnosis, verification="unverified", references=references,
                                   createdAt=datetime.now(timezone.utc).isoformat())]
        storage.save_state(state)
        await publish(incident_id, "reasoning", {"trace": state.reasoningTrace, "hypotheses": [item.model_dump() for item in state.hypotheses], "provider": state.providerStatus["qwen"],
            "span": {**llm_span, "ended_at": datetime.now(timezone.utc).isoformat(),
                     "duration_ms": llm_duration_ms, "status": state.providerStatus["qwen"], "model": llm_span["name"]}})
        await publish(incident_id, "action", {"diagnosis": state.diagnosis, "immediate_actions": state.immediateActions, "recommended_action": state.recommendedAction, "requires_approval": False})
    except Exception as error:
        state.providerStatus["investigation"] = "error"
        storage.save_state(state)
        await publish(incident_id, "error", {"message": "조사 흐름을 완료하지 못했습니다.",
            "kind": type(error).__name__, "stage": state.currentStep, "trace_id": state.traceId})
