from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from api.deps import get_current_user
from db.session import get_db_session
from db.models import WeightGoal
router=APIRouter()
class WeightGoalRequest(BaseModel):
    target_weight_kg: float = Field(gt=0, le=500)
    target_date: str|None = None
def _row(g): return None if not g else {"target_weight_kg":g.target_weight_kg,"target_date":g.target_date,"updated_at":g.updated_at}
@router.get("/")
def get_goal(current_user=Depends(get_current_user)):
    s=get_db_session()
    try:return _row(s.execute(select(WeightGoal).where(WeightGoal.user_id==current_user['id'])).scalar_one_or_none())
    finally:s.close()
@router.put("/")
def save_goal(req:WeightGoalRequest,current_user=Depends(get_current_user)):
    s=get_db_session(); now=datetime.now(timezone.utc).isoformat()
    try:
        goal=s.execute(select(WeightGoal).where(WeightGoal.user_id==current_user['id'])).scalar_one_or_none()
        if not goal: goal=WeightGoal(user_id=current_user['id'],target_weight_kg=req.target_weight_kg,target_date=req.target_date,created_at=now,updated_at=now);s.add(goal)
        else: goal.target_weight_kg=req.target_weight_kg;goal.target_date=req.target_date;goal.updated_at=now
        s.commit();return _row(goal)
    finally:s.close()
