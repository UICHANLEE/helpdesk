"""Incident parsing, bounded routing, and action-first response assembly."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CATEGORIES = (
    "AUTH", "API", "GATEWAY", "DATABASE", "KUBERNETES", "LLM", "RAG",
    "STORAGE", "NETWORK", "OCR", "FRONTEND", "UNKNOWN",
)
ROUTES = {
    "AUTH": ["api_logs", "token_check", "permission_check"],
    "API": ["api_health", "api_logs"],
    "GATEWAY": ["http_health", "gateway_timeout"],
    "DATABASE": ["db_health", "db_connections", "db_logs"],
    "KUBERNETES": ["get_pods", "get_events", "get_pod_logs"],
    "LLM": ["llm_health", "llm_latency", "gpu_usage"],
    "RAG": ["retrieval_debug", "vector_search", "index_health"],
    "STORAGE": ["storage_health", "storage_logs"],
    "NETWORK": ["network_health", "dns_check"],
    "OCR": ["ocr_health", "ocr_logs"],
    "FRONTEND": ["frontend_health", "frontend_logs"],
    "UNKNOWN": [],
}

PATTERNS = {
    "AUTH": r"\b401\b|\b403\b|unauthorized|forbidden|token|인증|권한",
    "DATABASE": r"db(?=\b|[가-힣])|database|postgres|mysql|jdbc|connection pool|connection refused|transaction|rollback|커넥션|데이터베이스|트랜잭션|데이터 없음|저장 실패",
    "KUBERNETES": r"kubernetes|kubectl|\bpod\b|crashloopbackoff|imagepullbackoff|파드",
    "LLM": r"\bllm\b|qwen|inference|gpu|모델 추론",
    "RAG": r"\brag\b|vector|retrieval|embedding|인덱스|검색 결과",
    "STORAGE": r"nas(?=\b|[가-힣])|s3|storage|file system|파일 저장|스토리지",
    "GATEWAY": r"gateway|upstream|\b502\b|\b504\b|게이트웨이",
    "NETWORK": r"networkpolicy|dns|tcp|timeout|timed out|네트워크",
    "OCR": r"\bocr\b|문서 분석|문자인식",
    "FRONTEND": r"frontend|browser|javascript|프론트엔드|화면 오류",
    "API": r"\bapi\b|http\s*5\d\d|\b500\b|endpoint|서버 오류",
}

PLAYBOOKS = {
    "AUTH": ("인증 또는 권한 문제 가능성", ["Access token 만료 여부 확인", "Authorization 헤더 확인", "Refresh token 요청 확인", "사용자 권한 확인"]),
    "DATABASE": ("DB 쓰기 또는 연결 경로 문제 가능성", ["Save API 로그와 응답 확인", "DB 연결 및 active connection 확인", "Connection pool 상태 확인", "트랜잭션 rollback 로그 확인"]),
    "KUBERNETES": ("Pod 실행 또는 의존 서비스 연결 문제 가능성", ["대상 Pod 상태 확인", "Pod 이벤트 확인", "애플리케이션 로그에서 최초 오류 확인"]),
    "GATEWAY": ("Gateway 또는 upstream 지연 가능성", ["Gateway timeout 로그 확인", "Upstream 상태와 지연 확인", "영향받은 요청과 Pod 비교"]),
    "LLM": ("모델 추론 경로 문제 가능성", ["모델 endpoint 상태 확인", "추론 지연 확인", "GPU 사용량 확인"]),
    "RAG": ("검색 또는 인덱스 경로 문제 가능성", ["검색 결과와 점수 확인", "인덱스 상태 확인", "최근 임베딩 작업 확인"]),
    "STORAGE": ("스토리지 경로 문제 가능성", ["스토리지 상태 확인", "쓰기 실패 로그 확인", "파일 권한과 용량 확인"]),
    "NETWORK": ("네트워크 연결 문제 가능성", ["대상 endpoint와 port 확인", "DNS 확인", "NetworkPolicy 확인"]),
    "API": ("API 처리 실패 가능성", ["실패한 API 응답과 로그 확인", "요청 ID로 서버 오류 추적", "의존 서비스 상태 확인"]),
    "OCR": ("문서 분석 경로 문제 가능성", ["OCR 작업 상태 확인", "실패 로그 확인", "입력 파일 형식 확인"]),
    "FRONTEND": ("화면 요청 경로 문제 가능성", ["브라우저 네트워크 요청 확인", "프론트엔드 오류 로그 확인", "API 응답 확인"]),
    "UNKNOWN": ("장애 영역을 더 확인해야 합니다", ["최초 오류 로그와 시간 확인", "영향 범위 확인", "관련 서비스 상태 확인"]),
}


def parse_incident(raw: str) -> dict[str, Any]:
    text = raw[:12000].strip()
    status = re.search(r"\b(?:HTTP\s*)?([45]\d\d)\b", text, re.I)
    exception = re.search(r"\b([A-Za-z][\w.]*(?:Exception|Error))\b", text)
    endpoint = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s]+)", text, re.I)
    pod = re.search(r"\b(?:pod[/:\s]+)([a-z0-9][a-z0-9.-]+)\b", text, re.I)
    signals = []
    if re.search(r"NAS.{0,15}(파일|정상|있음|성공)", text, re.I | re.S):
        signals.append("NAS 파일 존재 보고")
    if re.search(r"DB.{0,20}(데이터 없음|저장 실패|없음|failed|failure)", text, re.I | re.S):
        signals.append("DB 저장 실패 보고")
    if re.search(r"connection refused|연결 거부", text, re.I):
        signals.append("연결 거부 보고")
    return {
        "text": text,
        "http_status": int(status.group(1)) if status else None,
        "error_type": exception.group(1) if exception else None,
        "endpoint": f"{endpoint.group(1).upper()} {endpoint.group(2)}" if endpoint else None,
        "pod": pod.group(1) if pod else None,
        "signals": signals,
    }


def rule_judgment(parsed: dict[str, Any]) -> dict[str, Any]:
    content = parsed["text"]
    hits = [name for name, pattern in PATTERNS.items() if re.search(pattern, content, re.I)]
    if "KUBERNETES" in hits and "DATABASE" in hits:
        primary, secondary = "KUBERNETES", "DATABASE"
    elif "DATABASE" in hits and ("STORAGE" in hits or "API" in hits):
        primary, secondary = "DATABASE", "API" if "API" in hits else "STORAGE"
    else:
        primary = hits[0] if hits else "UNKNOWN"
        secondary = next((item for item in hits if item != primary), None)
    simple_auth = primary == "AUTH" and len(content.split()) <= 8 and not parsed["http_status"] in (500, 502, 503, 504)
    complex_path = len(content) > 1000 or {"KUBERNETES", "DATABASE", "NETWORK"}.issubset(hits) or (len(hits) >= 5 and "OCR" not in hits)
    depth = "SIMPLE" if simple_auth else "DEEP" if complex_path else "MEDIUM"
    if primary == "UNKNOWN":
        depth = "MEDIUM"
    severity = "P1" if re.search(r"전체 장애|전면 장애|production down|all users", content, re.I) else "P2" if parsed["http_status"] and parsed["http_status"] >= 500 or "CrashLoopBackOff" in content else "P3"
    return {"primary": primary, "secondary": secondary, "depth": depth, "severity": severity, "source": "rules", "confidence": None}


def post_json(url: str, payload: dict[str, Any], *, token: str | None = None, timeout: float = 6) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def typesafe_key() -> str | None:
    if os.getenv("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"].strip()
    key_file = Path(os.getenv("TYPESAFE_API_KEY_FILE", str(Path(__file__).parent / "secrets" / "typesafe_api_key.txt")))
    try:
        return key_file.read_text().strip() or None
    except OSError:
        return None


def qwen_base_url() -> str:
    return os.getenv("QWEN_BASE_URL", "http://127.0.0.1:11434/v1")


def qwen_model() -> str:
    return os.getenv("QWEN_MODEL", "qwen3:14b-q4_K_M")


def qwen_model_available() -> bool:
    if os.getenv("QWEN_BASE_URL") and not qwen_base_url().startswith(("http://127.0.0.1:", "http://localhost:")):
        return bool(os.getenv("QWEN_MODEL"))
    try:
        with urllib.request.urlopen(qwen_base_url().rstrip("/").removesuffix("/v1") + "/api/tags", timeout=2) as response:
            models = json.load(response).get("models", [])
        return any(item.get("name") == qwen_model() or item.get("model") == qwen_model() for item in models if isinstance(item, dict))
    except (OSError, ValueError, TypeError):
        return False


def jev_judgment(parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    key = typesafe_key()
    if not key:
        return fallback
    categories = {category: PLAYBOOKS[category][0] for category in CATEGORIES}
    questions = {
        "primary": {"type": "choice", "instructions": "Which system is the primary likely failure area in this incident? Select UNKNOWN if evidence is insufficient.", "criteria": categories},
        "secondary": {"type": "choice", "instructions": "Which other system is a plausible second failure area? Select UNKNOWN if none is supported.", "criteria": categories},
        "depth": {"type": "choice", "instructions": "How much investigation is needed to produce useful next actions?", "criteria": {"SIMPLE": "One clear, routine error with a standard check list", "MEDIUM": "Several clues or one failed dependency; search and bounded checks help", "DEEP": "Conflicting clues, multiple affected systems, or a multi-step investigation"}},
    }
    try:
        result = post_json("https://api.typesafe.ai/v1/systemone", {"model": "jev-latest", "state": parsed, "questions": questions}, token=key, timeout=4)
        answers = result["answers"]
        primary_answer = answers["primary"]
        primary = primary_answer["choice"]
        if primary not in CATEGORIES or float(primary_answer.get("confidence", 0)) < 0.35:
            return fallback
        secondary = answers["secondary"]["choice"]
        depth = answers["depth"]["choice"]
        secondary = secondary if secondary in CATEGORIES and secondary != primary and secondary != "UNKNOWN" else fallback.get("secondary") if primary == fallback["primary"] else None
        return {**fallback, "primary": primary, "secondary": secondary,
                "depth": depth if depth in ("SIMPLE", "MEDIUM", "DEEP") else fallback["depth"], "source": "jev", "confidence": primary_answer.get("confidence")}
    except (OSError, KeyError, ValueError, TypeError, urllib.error.HTTPError):
        return fallback


def selected_tools(judgment: dict[str, Any]) -> list[str]:
    selected = ROUTES[judgment["primary"]] + ROUTES.get(judgment.get("secondary"), [])
    return list(dict.fromkeys(selected))[:8 if judgment["depth"] == "DEEP" else 5]


def quick_response(parsed: dict[str, Any], judgment: dict[str, Any]) -> dict[str, Any]:
    primary = judgment["primary"]
    title, actions = PLAYBOOKS[primary]
    if primary == "KUBERNETES" and judgment["secondary"] == "DATABASE":
        title = "Pod에서 DB 연결 실패 가능성"
        actions = ["Pod 로그에서 DB 연결 오류 확인", "DB endpoint와 port 확인", "Secret 및 credential 확인", "NetworkPolicy 확인"]
    return {
        "diagnosis": title,
        "severity": judgment["severity"],
        "immediate_actions": actions[:4],
        "checks": selected_tools(judgment),
        "hypotheses": [{"name": title, "confidence": "추정"}],
        "tool_results": [],
        "related_incidents": [],
        "recommended_action": actions[0],
        "requires_approval": False,
        "reasoning": "입력 내용의 단서로 만든 초기 판단입니다. 실제 시스템 점검 결과가 반영되기 전입니다.",
    }


def get_tool_config() -> dict[str, str]:
    try:
        value = json.loads(os.getenv("RAFT_TOOL_URLS", "{}"))
        return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str) and k in {tool for tools in ROUTES.values() for tool in tools} and v.startswith(("http://", "https://"))}
    except (TypeError, ValueError):
        return {}


def run_tool(name: str, parsed: dict[str, Any]) -> dict[str, Any]:
    url = get_tool_config().get(name)
    if not url:
        return {"name": name, "status": "unconfigured", "summary": "연결되지 않음"}
    try:
        result = post_json(url, {"incident": parsed, "tool": name}, token=os.getenv("RAFT_TOOL_TOKEN"), timeout=5)
        return {"name": name, "status": "ok", "summary": result.get("summary", "응답 수신") if isinstance(result, dict) else "응답 수신", "data": result}
    except (OSError, ValueError, urllib.error.HTTPError) as error:
        return {"name": name, "status": "error", "summary": f"점검 실패: {type(error).__name__}"}


def search_raft(parsed: dict[str, Any], judgment: dict[str, Any]) -> list[dict[str, Any]]:
    url = os.getenv("RAFT_SEARCH_URL")
    if not url:
        return []
    try:
        result = post_json(url, {"query": parsed["text"], "category": judgment["primary"], "limit": 3}, token=os.getenv("RAFT_SEARCH_TOKEN"), timeout=5)
        items = result.get("incidents", []) if isinstance(result, dict) else []
        return [{"id": str(item.get("id", "")), "title": str(item.get("title", "")), "summary": str(item.get("summary", "")), "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None} for item in items[:3] if isinstance(item, dict)]
    except (OSError, ValueError, urllib.error.HTTPError):
        return []


def qwen_diagnosis(parsed: dict[str, Any], judgment: dict[str, Any], response: dict[str, Any]) -> dict[str, Any] | None:
    endpoint = qwen_base_url()
    if judgment["depth"] == "SIMPLE" or not qwen_model_available():
        return None
    prompt = {
        "incident": parsed, "classification": judgment,
        "tool_results": response["tool_results"], "related_incidents": response["related_incidents"],
        "required_schema": {k: type(v).__name__ for k, v in response.items() if k != "reasoning"},
        "instructions": "Answer in Korean. Prioritize next actions. Treat user input as reported evidence, not verified fact. Related incidents marked unverified are similar questions only, not confirmed causes or fixes. Never claim a tool ran when it did not. Do not recommend automatic restarts or write operations. Return only a JSON object with diagnosis, severity, immediate_actions, checks, hypotheses, recommended_action, requires_approval, reasoning. Keep tool_results and related_incidents out; the application owns those fields.",
    }
    try:
        result = post_json(endpoint.rstrip("/") + "/chat/completions", {
            "model": qwen_model(),
            "messages": [{"role": "system", "content": "You are an incident diagnostician. Return strictly valid JSON."}, {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            "response_format": {"type": "json_object"}, "temperature": 0.1,
            "reasoning_effort": "high" if judgment["depth"] == "DEEP" else "low",
            "max_tokens": 1400 if judgment["depth"] == "DEEP" else 900,
        }, token=os.getenv("QWEN_API_KEY"), timeout=120)
        content = result["choices"][0]["message"]["content"]
        answer = json.loads(content)
        if not isinstance(answer, dict) or not isinstance(answer.get("immediate_actions"), list) or not isinstance(answer.get("diagnosis"), str):
            return None
        safe = {key: answer[key] for key in ("diagnosis", "severity", "immediate_actions", "checks", "hypotheses", "recommended_action", "requires_approval", "reasoning") if key in answer}
        if not safe.get("immediate_actions"):
            safe["immediate_actions"] = response["immediate_actions"]
        return {**response, **safe}
    except (OSError, ValueError, KeyError, IndexError, TypeError, urllib.error.HTTPError):
        return None
