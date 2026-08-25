from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from api.deps import get_current_user
from services.analytics import get_user_scope_user_ids
from services.health_observation_service import list_observations

router = APIRouter()

@router.get("/", summary="List structured health observations in the current user's scope")
def list_endpoint(current_user=Depends(get_current_user), category: Optional[str] = None, name: Optional[str] = None,
                  document_id: Optional[int] = Query(None, ge=1), date_from: Optional[str] = None, date_to: Optional[str] = None,
                  status: Optional[str] = None):
    return list_observations(get_user_scope_user_ids(current_user), category=category, name=name,
                             document_id=document_id, date_from=date_from, date_to=date_to, status=status)

@router.get("/{observation_id}", summary="Get a structured health observation")
def get_endpoint(observation_id: int, current_user=Depends(get_current_user)):
    rows = list_observations(get_user_scope_user_ids(current_user))
    observation = next((row for row in rows if row["id"] == observation_id), None)
    if not observation:
        raise HTTPException(status_code=404, detail="Health observation not found")
    return observation
