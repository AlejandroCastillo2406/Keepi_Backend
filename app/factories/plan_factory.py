from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.subscription.plan_admin_service import PlanAdminService


def get_plan_admin_service(db: Session = Depends(get_db)) -> PlanAdminService:
    return PlanAdminService(db)
