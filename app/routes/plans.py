from fastapi import APIRouter, Depends, status

from app.core.security import require_no_temp_password_user
from app.models.user import User
from app.models.plans import PlanCreate, PlanUpdate, PlanResponse
from app.factories.plan_factory import get_plan_admin_service
from app.services.subscription.plan_admin_service import PlanAdminService

router = APIRouter(tags=["Admin Plans"])


def check_admin_user(current_user: User = Depends(require_no_temp_password_user)):
    return current_user


@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan_in: PlanCreate,
    current_user: User = Depends(check_admin_user),
    svc: PlanAdminService = Depends(get_plan_admin_service),
):
    return svc.create_plan(plan_in)


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    current_user: User = Depends(check_admin_user),
    svc: PlanAdminService = Depends(get_plan_admin_service),
):
    return svc.get_plan(plan_id)


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: str,
    plan_in: PlanUpdate,
    current_user: User = Depends(check_admin_user),
    svc: PlanAdminService = Depends(get_plan_admin_service),
):
    return svc.update_plan(plan_id, plan_in)


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(check_admin_user),
    svc: PlanAdminService = Depends(get_plan_admin_service),
):
    return svc.deactivate_plan(plan_id)
