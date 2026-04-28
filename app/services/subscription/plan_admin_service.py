from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.plans import Plan, PlanCreate, PlanResponse, PlanUpdate
from app.repositories.plan_repository import PlanRepository


class PlanAdminService:
    def __init__(
        self, db: Session, plan_repository: PlanRepository | None = None
    ) -> None:
        self._db = db
        self._plans = plan_repository or PlanRepository(db)

    def create_plan(self, plan_in: PlanCreate) -> PlanResponse:
        if self._plans.get_by_code(plan_in.code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un plan con ese código",
            )
        plan = Plan(
            code=plan_in.code,
            name=plan_in.name,
            description=plan_in.description,
            price=plan_in.price,
            currency=plan_in.currency,
            interval=plan_in.interval,
            stripe_price_id=plan_in.stripe_price_id,
            analysis_limit=plan_in.analysis_limit,
            features=plan_in.features or [],
            is_active=plan_in.is_active,
            recommended=plan_in.recommended,
        )
        saved = self._plans.add(plan)
        return PlanResponse.from_orm(saved)

    def get_plan(self, plan_id: str) -> PlanResponse:
        try:
            pid = uuid.UUID(plan_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="plan_id inválido") from exc
        plan = self._plans.get_by_id(pid)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan no encontrado")
        return PlanResponse.from_orm(plan)

    def update_plan(self, plan_id: str, plan_in: PlanUpdate) -> PlanResponse:
        try:
            pid = uuid.UUID(plan_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="plan_id inválido") from exc
        plan = self._plans.get_by_id(pid)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan no encontrado")

        data = plan_in.model_dump(exclude_unset=True)
        if "code" in data and data["code"] != plan.code:
            other = self._plans.get_by_code(data["code"])
            if other and other.id != plan.id:
                raise HTTPException(
                    status_code=400,
                    detail="Ya existe otro plan con ese código",
                )
        for key, value in data.items():
            setattr(plan, key, value)
        saved = self._plans.save(plan)
        return PlanResponse.from_orm(saved)

    def deactivate_plan(self, plan_id: str) -> dict:
        try:
            pid = uuid.UUID(plan_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="plan_id inválido") from exc
        plan = self._plans.get_by_id(pid)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan no encontrado")
        plan.is_active = False
        self._plans.save(plan)
        return {"message": "Plan desactivado correctamente", "plan_id": plan_id}
