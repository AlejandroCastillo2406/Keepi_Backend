from __future__ import annotations

import uuid
from typing import List, Optional, Union

from sqlalchemy.orm import Session, joinedload

from app.models.role import Role
from app.models.user import User

from datetime import datetime, timezone

from sqlalchemy import case, func
from app.models.appointment import Appointment
from app.models.document import Document
from app.models.doctor_patient_clinical_profile import DoctorPatientClinicalProfile

class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def role_id_by_name(self, name: str) -> Optional[int]:
        row = self._db.query(Role).filter(Role.name == name).first()
        return int(row.id) if row else None

    def get_by_id_with_role(self, uid: Union[str, uuid.UUID]) -> Optional[User]:
        try:
            u = uuid.UUID(str(uid))
        except (ValueError, TypeError):
            return None
        return (
            self._db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == u)
            .first()
        )

    def get_by_id_plain(self, uid: Union[str, uuid.UUID]) -> Optional[User]:
        try:
            u = uuid.UUID(str(uid))
        except (ValueError, TypeError):
            return None
        return self._db.query(User).filter(User.id == u).first()

    def email_exists(self, email: str) -> bool:
        return (
            self._db.query(User).filter(User.email == email.strip()).first() is not None
        )

    def get_by_email_with_role(self, email: str) -> Optional[User]:
        return (
            self._db.query(User)
            .options(joinedload(User.role))
            .filter(User.email == email)
            .first()
        )

    def add(self, user: User) -> None:
        self._db.add(user)

    def flush(self) -> None:
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, user: User) -> None:
        self._db.refresh(user)

    def rollback(self) -> None:
        self._db.rollback()

    def reload_with_role(self, user_id: Union[str, uuid.UUID]) -> Optional[User]:
        return self.get_by_id_with_role(user_id)

    def list_all_with_role(self) -> List[User]:
        return self._db.query(User).options(joinedload(User.role)).all()

    def delete(self, user: User) -> None:
        self._db.delete(user)
        self._db.commit()

    def list_created_by_with_role(
        self, doctor_id: uuid.UUID, patient_role_id: int
    ) -> List[User]:
        return (
            self._db.query(User)
            .filter(
                User.created_by_user_id == doctor_id,
                User.role_id == patient_role_id,
                User.is_active.is_(True),
            )
            .order_by(User.created_at.desc())
            .all()
        )

    def get_patient_owned_by_doctor(
        self,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> Optional[User]:
        query = self._db.query(User).filter(
            User.id == patient_id,
            User.created_by_user_id == doctor_id,
        )
        if active_only:
            query = query.filter(User.is_active.is_(True))
        return query.first()

    def set_active(self, user: User, active: bool) -> None:
        user.is_active = active
        self._db.commit()
        self._db.refresh(user)
        
    def list_created_by_with_patient_summary(
        self,
        doctor_id: uuid.UUID,
        patient_role_id: int,
    ):
        now = datetime.now(timezone.utc)

        appt_summary = (
            self._db.query(
                Appointment.patient_id.label("patient_id"),
                func.count(Appointment.id).label("appointments_total"),
                func.sum(
                    case(
                        (Appointment.attendance_status == "attended", 1),
                        else_=0,
                    )
                ).label("appointments_attended"),
                func.sum(
                    case(
                        (Appointment.attendance_status == "no_show", 1),
                        else_=0,
                    )
                ).label("appointments_no_show"),
                func.sum(
                    case(
                        (
                            (Appointment.status == "scheduled")
                            & (Appointment.attendance_status.is_(None))
                            & (Appointment.appointment_date < now),
                            1,
                        ),
                        else_=0,
                    )
                ).label("appointments_pending_attendance"),
                func.max(
                    case(
                        (Appointment.appointment_date < now, Appointment.appointment_date),
                        else_=None,
                    )
                ).label("last_appointment_date"),
                func.min(
                    case(
                        (Appointment.appointment_date >= now, Appointment.appointment_date),
                        else_=None,
                    )
                ).label("next_appointment_date"),
            )
            .filter(Appointment.doctor_id == doctor_id)
            .filter(Appointment.status != "canceled")
            .group_by(Appointment.patient_id)
            .subquery()
        )

        doc_summary = (
            self._db.query(
                Document.user_id.label("patient_id"),
                func.count(Document.id).label("documents_total"),
            )
            .filter(Document.is_archived.is_(False))
            .group_by(Document.user_id)
            .subquery()
        )

        return (
            self._db.query(
                User,
                DoctorPatientClinicalProfile,
                appt_summary.c.appointments_total,
                appt_summary.c.appointments_attended,
                appt_summary.c.appointments_no_show,
                appt_summary.c.appointments_pending_attendance,
                appt_summary.c.last_appointment_date,
                appt_summary.c.next_appointment_date,
                doc_summary.c.documents_total,
            )
            .outerjoin(
                DoctorPatientClinicalProfile,
                (DoctorPatientClinicalProfile.patient_id == User.id)
                & (DoctorPatientClinicalProfile.doctor_id == doctor_id),
            )
            .outerjoin(appt_summary, appt_summary.c.patient_id == User.id)
            .outerjoin(doc_summary, doc_summary.c.patient_id == User.id)
            .filter(
                User.created_by_user_id == doctor_id,
                User.role_id == patient_role_id,
                User.is_active.is_(True),
            )
            .order_by(User.created_at.desc())
            .all()
        )
