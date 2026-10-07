from fastapi import APIRouter, HTTPException

from backend.agent.orchestrator import start
from backend.models import DiagnoseRequest, DiagnoseResponse

router = APIRouter()


@router.post("/diagnose", response_model=DiagnoseResponse, status_code=201)
async def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    if request.attachments:
        raise HTTPException(status_code=422, detail="Attachments are not supported in this MVP")
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문이나 장애 상황을 입력하세요.")
    try:
        incident_id, classification = await start(request.message.strip(), request.incident_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return DiagnoseResponse(incident_id=incident_id, classification=classification)
