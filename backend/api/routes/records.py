import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel

from services.records import list_records, create_record_from_form, update_record_from_form, delete_record_by_id
from services.notification_service import create_notification
from api.deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class RecordCreateRequest(BaseModel):
    record_date: str
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    food: Optional[str] = None
    calories: Optional[float] = None
    water_liters: Optional[float] = None
    sleep_hours: Optional[float] = None
    exercise: Optional[str] = None
    target_user_id: Optional[int] = None


@router.get("/", summary="List records in current user's scope")
def list_records_endpoint(
    search: str = Query(default="", description="Search in food/exercise"),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    sort: str = Query(default="record_date desc"),
    current_user=Depends(get_current_user),
):
    # Scope handled inside services/records.py through user_ids.
    from services.analytics import get_user_scope_user_ids

    user_ids = get_user_scope_user_ids(current_user)
    return list_records(user_ids, search=search, sort=sort, filters={"from_date": from_date, "to_date": to_date})


@router.post("/", summary="Create record")
def create_record(req: RecordCreateRequest, current_user=Depends(get_current_user)):
    if req.target_user_id is None:
        target_user_id = current_user["id"]
    else:
        # basic role validation
        if current_user["role"] == "User":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        target_user_id = req.target_user_id

    rec = {
        "record_date": req.record_date,
        "height_cm": req.height_cm,
        "weight_kg": req.weight_kg,
        "food": req.food,
        "calories": req.calories,
        "water_liters": req.water_liters,
        "sleep_hours": req.sleep_hours,
        "exercise": req.exercise,
        "target_user_id": target_user_id,
        "created_by_user_id": current_user["id"],
    }
    new_id = create_record_from_form(rec)
    try:
        create_notification(
            target_user_id,
            title="New health record added",
            message=str(rec.get("record_date") or ""),
            type="record",
            data={"record_id": new_id},
        )
    except Exception:
        logger.exception("Failed to create record-created notification for record %d", new_id)
    return {"id": new_id}


@router.put("/{record_id}", summary="Update record")
def update_record(record_id: int, req: RecordCreateRequest, current_user=Depends(get_current_user)):
    from services.analytics import get_user_scope_user_ids
    user_ids = get_user_scope_user_ids(current_user)

    rec = {
        "record_date": req.record_date,
        "height_cm": req.height_cm,
        "weight_kg": req.weight_kg,
        "food": req.food,
        "calories": req.calories,
        "water_liters": req.water_liters,
        "sleep_hours": req.sleep_hours,
        "exercise": req.exercise,
    }

    try:
        updated_id = update_record_from_form(record_id, rec, user_ids)
        try:
            create_notification(
                current_user["id"],
                title="Health record updated",
                message=str(rec.get("record_date") or ""),
                type="record",
                data={"record_id": updated_id},
            )
        except Exception:
            logger.exception("Failed to create record-updated notification for record %d", updated_id)
        return {"id": updated_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{record_id}", summary="Delete record")
def delete_record(record_id: int, current_user=Depends(get_current_user)):
    from services.analytics import get_user_scope_user_ids
    user_ids = get_user_scope_user_ids(current_user)

    try:
        delete_record_by_id(record_id, user_ids)
        return {"ok": True, "message": "Record deleted"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

