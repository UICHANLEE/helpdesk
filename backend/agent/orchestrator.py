from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any, AsyncIterator

from incident import get_tool_config, quick_response, qwen_model, qwen_model_available

from backend.agent.jev import classify
from backend.llm.qwen import diagnose as qwen_diagnose
from backend.models import AgentAction, Classification, Evidence, Hypothesis, IncidentState, IncidentStatus, RaftMatch
from backend.raft.retriever import retrieve
from backend.storage import sqlite as storage
from backend.tools.registry import execute, tools_for

_conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
_tasks: set[asyncio.Task] = set()


def classification_from(judgment: dict[str, Any]) -> Classification:
    return Classification(domain=judgment["primary"], secondary=judgment.get("secondary"), severity=judgment["severity"], complexity=judgment["depth"], source=judgment["source"], confidence=judgment.get("confidence"))


async def publish(incident_id: str, event_type: str, data: dict[str, Any]) -> None:
    storage.append_event(incident_id, event_type, data)
    async with _conditions[incident_id]:
        _conditions[incident_id].notify_all()


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
    parsed, judgment = await classify(message)
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
    await publish(incident_id, "user", {"message": message})
    await publish(incident_id, "jev", {"classification": classification.model_dump(), "parsed": {k: v for k, v in parsed.items() if k != "text"}})
    task = asyncio.create_task(investigate(incident_id, parsed, judgment))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return incident_id, classification


async def investigate(incident_id: str, parsed: dict[str, Any], judgment: dict[str, Any]) -> None:
    record = storage.get_incident(incident_id)
    if not record:
        return
    state = IncidentState.model_validate(record["state"])
    try:
        state.currentStep = "retrieve"
        storage.save_state(state)
        matches = await retrieve(parsed, judgment)
        state.raftMatches = [RaftMatch.model_validate(item) for item in matches]
        state.providerStatus["raft"] = "connected" if os.getenv("RAFT_SEARCH_URL") else "local_history"
        storage.save_state(state)
        await publish(incident_id, "retrieval", {"matches": [match.model_dump() for match in state.raftMatches], "status": state.providerStatus["raft"]})

        tools = tools_for(judgment)
        configured_tools = get_tool_config()
        results: list[dict[str, Any]] = []
        for tool in tools:
            if tool in configured_tools:
                await publish(incident_id, "tool_started", {"tool": tool})
            result = await execute(tool, parsed)
            results.append(result)
            evidence = Evidence(id=f"E{len(results)}", source=tool, summary=str(result["summary"]), status="confirmed" if result["status"] == "ok" else "unavailable", data=result.get("data") if isinstance(result.get("data"), dict) else None)
            if evidence.status == "confirmed":
                state.confirmedFacts.append(evidence)
            storage.save_state(state)
            await publish(incident_id, "tool_result", {"tool": tool, "result": result, "evidence": evidence.model_dump()})

        state.currentStep = "reason"
        storage.save_state(state)
        context = quick_response(parsed, judgment)
        context["tool_results"] = results
        context["related_incidents"] = matches
        if state.providerStatus.get("qwen") == "pending":
            await publish(incident_id, "reasoning_started", {"model": qwen_model(), "complexity": judgment["depth"]})
        answer = await qwen_diagnose(parsed, judgment, context)
        final = answer or context
        state.providerStatus["qwen"] = "connected" if answer else "skipped" if judgment["depth"] == "SIMPLE" else "unavailable"
        state.diagnosis = str(final.get("diagnosis") or context["diagnosis"])
        state.immediateActions = [str(item) for item in final.get("immediate_actions", [])][:6] or context["immediate_actions"]
        state.recommendedAction = str(final.get("recommended_action") or state.immediateActions[0])
        state.hypotheses = [Hypothesis(id=f"H{i+1}", name=str(item.get("name", "확인 필요")), confidence=item.get("confidence") if isinstance(item.get("confidence"), (int, float)) else None, rationale=str(item.get("rationale", ""))) for i, item in enumerate(final.get("hypotheses", [])) if isinstance(item, dict)]
        state.reasoningTrace = [
            {"step": "OBSERVATION", "text": "; ".join(state.symptoms)},
            {"step": "INTERPRETATION", "text": state.classification.domain if state.classification else "UNKNOWN"},
            {"step": "EVIDENCE", "text": "; ".join(item.summary for item in state.confirmedFacts) or "연결된 도구의 확인 결과 없음"},
            {"step": "HYPOTHESIS", "text": state.diagnosis},
            {"step": "NEXT TEST", "text": state.recommendedAction},
        ]
        state.actions = [AgentAction(id=f"{incident_id}-A1", label=state.recommendedAction, requires_approval=bool(final.get("requires_approval", False)))]
        state.status = IncidentStatus.action_required
        state.currentStep = "act"
        storage.save_state(state)
        await publish(incident_id, "reasoning", {"trace": state.reasoningTrace, "hypotheses": [item.model_dump() for item in state.hypotheses], "provider": state.providerStatus["qwen"]})
        await publish(incident_id, "action", {"diagnosis": state.diagnosis, "immediate_actions": state.immediateActions, "recommended_action": state.recommendedAction, "requires_approval": False})
    except Exception as error:
        state.providerStatus["investigation"] = "error"
        storage.save_state(state)
        await publish(incident_id, "error", {"message": "조사 흐름을 완료하지 못했습니다.", "kind": type(error).__name__})
