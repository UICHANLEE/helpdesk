"""Build an audit view from durable incident events and explicit claim references."""

from __future__ import annotations

from typing import Any


def graph(incident: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    incident_id = incident["id"]
    state = incident["state"]
    trace_id = state.get("traceId") or f"TR-{incident_id}"
    spans: dict[str, dict[str, Any]] = {trace_id: {
        "id": trace_id, "trace_id": trace_id, "parent_span_id": None, "kind": "request",
        "name": "Incident investigation", "status": state.get("status", "unknown"),
        "started_at": incident["created_at"], "ended_at": incident["updated_at"],
    }}
    evidence = []
    edges = []
    for event in events:
        data = event["data"]
        trace = (data.get("span") or data.get("trace")) if isinstance(data, dict) else None
        span_id = trace.get("span_id") if isinstance(trace, dict) else None
        if span_id:
            span = spans.setdefault(span_id, {"id": span_id, "trace_id": trace_id})
            span.update({key: value for key, value in trace.items() if value is not None})
            span["last_event_id"] = event["id"]
        if event["type"] not in ("user", "tool_result", "retrieval", "status_changed"):
            continue
        if event["type"] == "status_changed" and data.get("status") != "resolved":
            continue
        evidence_id = f"EV-{event['id']}"
        if event["type"] == "user":
            summary = str(data.get("message") or "사용자 요청")
            status = "reported"
        elif event["type"] == "tool_result":
            result = data.get("result") or {}
            summary = str(result.get("summary") or "")
            status = str(result.get("status") or "unknown")
        elif event["type"] == "retrieval":
            summary = f"과거 사례 {len(data.get('matches') or [])}건 검색"
            status = "historical"
        else:
            summary = str((data.get("resolution") or {}).get("rootCause") or "운영자 해결 확인")
            status = "operator_verified"
        evidence.append({"id": evidence_id, "event_id": event["id"], "kind": event["type"],
                         "summary": summary, "status": status, "span_id": span_id})
        if span_id:
            edges.append({"from": evidence_id, "to": span_id, "relation": "observed_in"})
    for claim in state.get("claims") or []:
        for reference in claim.get("references") or []:
            edges.append({"from": claim["id"], "to": f"EV-{reference['eventId']}",
                          "relation": reference["relation"]})
    tool_spans = [item for item in spans.values() if item.get("kind") == "tool"]
    failures = sum(item.get("status") == "error" for item in tool_spans)
    unconfigured = sum(item.get("status") == "unconfigured" for item in tool_spans)
    slowest = max((item for item in spans.values() if isinstance(item.get("duration_ms"), (int, float))),
                  key=lambda item: item["duration_ms"], default=None)
    return {"trace_id": trace_id, "spans": list(spans.values()),
            "evidence": evidence, "claims": state.get("claims") or [], "edges": edges,
            "signals": {"tool_failures": failures, "unconfigured_tools": unconfigured,
                        "confirmed_checks": sum(item.get("status") == "ok" for item in tool_spans),
                        "slowest_span": {"id": slowest["id"], "name": slowest.get("name"),
                                         "duration_ms": slowest["duration_ms"]} if slowest else None}}
