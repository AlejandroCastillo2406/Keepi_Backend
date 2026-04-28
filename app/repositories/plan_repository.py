from __future__ import annotations

import uuid
from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.models.plans import Plan


class PlanRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, plan_id: Union[str, uuid.UUID]) -> Optional[Plan]:
        try:
            pid = uuid.UUID(str(plan_id))
        except (ValueError, TypeError):
            return None
        return self._db.query(Plan).filter(Plan.id == pid).first()

    def get_by_code(self, code: str) -> Optional[Plan]:
        return self._db.query(Plan).filter(Plan.code == code).first()

    def list_active_ordered_by_price(self) -> List[Plan]:
        return (
            self._db.query(Plan)
            .filter(Plan.is_active.is_(True))
            .order_by(Plan.price.asc())
            .all()
        )

    def add(self, plan: Plan) -> Plan:
        self._db.add(plan)
        self._db.commit()
        self._db.refresh(plan)
        return plan

    def save(self, plan: Plan) -> Plan:
        self._db.commit()
        self._db.refresh(plan)
        return plan
