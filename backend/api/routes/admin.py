from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List

from api.deps import get_current_user, require_role
from services.admin import list_users as svc_list_users, create_user, update_user, delete_user, assign_staff_to_user
from services.staff import list_assigned_users
from services.analytics import get_user_scope_user_ids

import os
from db.session import DB_PATH, engine

router = APIRouter()



class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str


class AssignStaffRequest(BaseModel):
    staff_id: int
    user_id: int


@router.get("/users", summary="List all users (Admin only)")
def list_users_endpoint(current_user=Depends(require_role({"Admin"}))):
    print("===== GET /admin/users Request Debug =====")
    print("CWD:", os.getcwd())
    print("HEALTH_DB_PATH:", os.environ.get("HEALTH_DB_PATH"))
    print("Resolved DB_PATH:", DB_PATH)
    print("Engine URL:", engine.url)

    users_before = svc_list_users()
    print("User count (GET returned):", len(users_before))
    if users_before:
        print("Last username in response:", users_before[-1].get("username"))

    return users_before



@router.post("/users", summary="Create user (Admin only)")
def create_user_endpoint(req: UserCreateRequest, current_user=Depends(require_role({"Admin"}))):
    print("===== POST /admin/users Request Debug =====")
    print("CWD:", os.getcwd())
    print("HEALTH_DB_PATH:", os.environ.get("HEALTH_DB_PATH"))
    print("Resolved DB_PATH:", DB_PATH)
    print("Engine URL:", engine.url)

    users_before = svc_list_users()
    print("User count (GET before POST):", len(users_before))
    if users_before:
        print("Last username before POST:", users_before[-1].get("username"))

    print("Creating username:", (req.username or "").strip())

    try:
        new_id = create_user(req.username, req.password, req.role)

        users_after = svc_list_users()
        print("User count (after POST):", len(users_after))
        if users_after:
            print("Last username after POST:", users_after[-1].get("username"))

        return {"id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.post("/assign", summary="Assign staff to a user (Admin only)")
def assign_staff(req: AssignStaffRequest, current_user=Depends(require_role({"Admin"}))):
    assign_staff_to_user(req.staff_id, req.user_id)
    return {"ok": True}


@router.get("/staff/assigned", summary="List users assigned to current staff")
def staff_assigned_endpoint(current_user=Depends(require_role({"Admin", "Staff"}))):
    return list_assigned_users(current_user)


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


@router.put("/users/{user_id}", summary="Update user (Admin only)")
def update_user_endpoint(
    user_id: int,
    req: UserUpdateRequest,
    current_user=Depends(require_role({"Admin"})),
):
    if req.username is None and req.role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    try:
        ok = update_user(user_id, username=req.username, role=req.role)
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/users/{user_id}", summary="Delete user (Admin only)")
def delete_user_endpoint(
    user_id: int,
    current_user=Depends(require_role({"Admin"})),
):
    # Prevent admin from deleting themselves
    if current_user["id"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}

