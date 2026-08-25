from fastapi import APIRouter, Depends
from api.deps import get_current_user
from services.analytics import get_user_scope_user_ids
from services.health_intelligence import build_overview
router = APIRouter()
@router.get("/", summary="Deterministic personal health metrics, trends, and source-attributed alerts")
def overview(current_user=Depends(get_current_user)):
    return build_overview(get_user_scope_user_ids(current_user))
