from fastapi import APIRouter, HTTPException

from backend.agent.orchestrator import start
from backend.models import DiagnoseRequest, DiagnoseResponse

router = APIRouter()


@router.post("/diagnose", response_model=DiagnoseResponse, status_code=201)
async def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    if request.attachments:
        raise HTTPException(status_code=422, detail="Attachments are not supported in this MVP")
    incident_id, classification = await start(request.message)
    return DiagnoseResponse(incident_id=incident_id, classification=classification)
