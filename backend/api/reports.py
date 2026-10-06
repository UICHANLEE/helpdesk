from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.reports import daily
from backend.storage import backup

router = APIRouter()


@router.get("/reports/storage")
def storage_status() -> dict:
    return backup.status()


@router.post("/reports/backup")
def create_backup() -> dict:
    return backup.backup_now()


@router.get("/reports/daily")
def days() -> list[dict]:
    return [{key: value for key, value in daily.report(day).items() if key != "records"} for day in daily.available_days()]


@router.get("/reports/daily/{day}")
def day_report(day: str) -> dict:
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Use YYYY-MM-DD") from None
    return daily.report(day)


@router.get("/reports/daily/{day}/xlsx")
def download(day: str) -> FileResponse:
    try:
        path = daily.export(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Use YYYY-MM-DD") from None
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=path.name)
