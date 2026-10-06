from fastapi import APIRouter

from backend.storage import supabase

router = APIRouter()


@router.get("/sync/status")
def status() -> dict:
    return supabase.status()


@router.post("/sync/flush")
def flush() -> dict:
    return supabase.flush()
