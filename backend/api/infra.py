import os

from fastapi import APIRouter

from incident import get_tool_config, qwen_model_available, typesafe_key
from backend.storage.supabase import status as supabase_status

router = APIRouter()


@router.get("/infrastructure/overview")
def overview() -> dict:
    configured = get_tool_config()
    groups = {
        "kubernetes": ["get_pods", "get_events"],
        "database": ["db_health", "db_connections"],
        "api": ["api_health", "http_health"],
        "llm": ["llm_health", "llm_latency"],
        "storage": ["storage_health"],
    }
    services = [{"name": name, "status": "configured" if any(tool in configured for tool in tools) else "unconfigured", "note": "상태를 확인하려면 진단에서 점검을 실행하세요."} for name, tools in groups.items()]
    return {"services": services, "qwen": "configured" if qwen_model_available() else "unavailable", "jev": "configured" if typesafe_key() else "unconfigured", "raft": "configured" if os.getenv("RAFT_SEARCH_URL") else "local_history", "supabase": supabase_status()}
