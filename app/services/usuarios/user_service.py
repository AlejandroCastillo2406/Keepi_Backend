import secrets
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.auth.jwt_payloads import access_token_claims_for_user
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT, ROLE_USER
from app.models.patient_medical_record import MedicalRecordInitialData, PatientMedicalRecord
from app.models.role import Role
from app.models.user import (User, UserCreate, UserLogin, UserResponse,
                             UserUpdate)
from app.utils.auth import (create_access_token, create_refresh_token,
                            get_password_hash, verify_password)


class UserService:
    """Servicio para gestión de usuarios."""

    def __init__(self, db: Session):
        self.db = db

    def role_id_by_name(self, name: str) -> int:
        row = self.db.query(Role).filter(Role.name == name).first()
        if row is None:
            raise ValueError(f"Rol no encontrado en BD: {name}")
        return row.id

    def get_user_orm_by_uid(self, uid: str) -> Optional[User]:
        """Obtener usuario ORM por UID (para verificar refresh_token, etc.)."""
        try:
            return (
                self.db.query(User)
                .options(joinedload(User.role))
                .filter(User.id == uid)
                .first()
            )
        except Exception as e:
            print(f"Error obteniendo usuario: {e}")
            return None

    async def get_user_by_uid(self, uid: str) -> Optional[UserResponse]:
        """Obtener usuario por UID"""
        try:
            user = (
                self.db.query(User)
                .options(joinedload(User.role))
                .filter(User.id == uid)
                .first()
            )
            if user:
                return UserResponse.from_orm(user)
            return None
        except Exception as e:
            print(f"Error obteniendo usuario: {e}")
            return None

    async def create_user(self, user_data: UserCreate) -> User:
        """Crear nuevo usuario (autoregistro como USER o DOCTOR)."""
        try:
            existing_user = self.db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                raise ValueError("El usuario con este email ya existe")

            role_key = user_data.role_name
            if role_key not in (ROLE_USER, ROLE_DOCTOR):
                raise ValueError("Solo puedes registrarte como usuario o como médico")
            rid = self.role_id_by_name(role_key)
            user = User(
                email=user_data.email,
                name=user_data.name,
                hashed_password=get_password_hash(user_data.password) if user_data.password else None,
                role_id=rid,
                must_change_password=False,
            )

            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return (
                self.db.query(User)
                .options(joinedload(User.role))
                .filter(User.id == user.id)
                .first()
            )
        except Exception as e:
            print(f"Error creando usuario: {e}")
            self.db.rollback()
            raise

    async def create_patient_by_doctor(
        self,
        doctor: User,
        email: str,
        name: str,
        medical_record: MedicalRecordInitialData,
    ) -> Tuple[User, str]:
        """
        Crea paciente con contraseña temporal, expediente médico y must_change_password=True.
        Transacción única: usuario + expediente (columnas alineadas con BD existente).
        """
        if doctor.role is None or doctor.role.name != ROLE_DOCTOR:
            raise PermissionError("Solo un usuario con rol DOCTOR puede crear pacientes")

        existing = self.db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("Ya existe un usuario con este email")

        plain = secrets.token_urlsafe(16)
        rid = self.role_id_by_name(ROLE_PATIENT)
        user = User(
            email=email,
            name=name,
            hashed_password=get_password_hash(plain),
            role_id=rid,
            must_change_password=True,
            created_by_user_id=doctor.id,
        )
        self.db.add(user)
        self.db.flush()

        mr = medical_record
        pmr = PatientMedicalRecord(
            patient_user_id=user.id,
            created_by_user_id=doctor.id,
            birth_date=mr.birth_date,
            sex=mr.sex,
            blood_type=mr.blood_type,
            allergies=mr.allergies,
            chronic_conditions=mr.chronic_conditions,
            medications=mr.medications,
            surgical_history=mr.surgical_history,
            family_history=mr.family_history,
            notes=mr.notes,
            emergency_contact_name=mr.emergency_contact_name,
            emergency_contact_phone=mr.emergency_contact_phone,
        )
        self.db.add(pmr)
        self.db.commit()
        self.db.refresh(user)

        loaded = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user.id)
            .first()
        )
        if loaded is None:
            raise RuntimeError("No se pudo recargar el paciente creado")
        return loaded, plain

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        user = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user_id)
            .first()
        )
        if user is None:
            raise ValueError("Usuario no encontrado")
        if not user.hashed_password:
            raise ValueError("Este usuario no tiene contraseña local")
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("La contraseña actual no es correcta")

        user.hashed_password = get_password_hash(new_password)
        user.must_change_password = False
        self.db.commit()
        self.db.refresh(user)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        try:
            user = (
                self.db.query(User)
                .options(joinedload(User.role))
                .filter(User.email == email)
                .first()
            )
            if not user:
                return None
            if not user.hashed_password:
                return None
            if not verify_password(password, user.hashed_password):
                return None
            return user
        except Exception as e:
            print(f"Error autenticando usuario: {e}")
            return None

    async def login_user(self, login_data: UserLogin) -> Optional[Dict[str, Any]]:
        """Login de usuario y retornar token"""
        try:
            user = await self.authenticate_user(login_data.email, login_data.password)
            if not user:
                return None

            access_token_expires = timedelta(minutes=30)
            claims = access_token_claims_for_user(user)
            access_token = create_access_token(
                data=claims,
                expires_delta=access_token_expires,
            )

            refresh_token = create_refresh_token(claims)

            user.refresh_token = refresh_token
            self.db.commit()

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": 30 * 60,
                "must_change_password": user.must_change_password,
                "role_id": user.role_id,
                "role_name": user.role.name if user.role else "",
                "user": UserResponse.from_orm(user),
            }
        except Exception as e:
            print(f"Error en login: {e}")
            return None

    async def update_user(self, uid: str, user_data: UserUpdate) -> Optional[UserResponse]:
        """Actualizar usuario"""
        try:
            user = (
                self.db.query(User)
                .options(joinedload(User.role))
                .filter(User.id == uid)
                .first()
            )
            if not user:
                return None

            update_data = user_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(user, field, value)

            self.db.commit()
            self.db.refresh(user)

            return UserResponse.from_orm(user)
        except Exception as e:
            print(f"Error actualizando usuario: {e}")
            self.db.rollback()
            return None

    async def update_user_fields(self, uid: str, fields: dict) -> bool:
        """Actualizar campos específicos del usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if not user:
                return False

            for field, value in fields.items():
                if hasattr(user, field):
                    setattr(user, field, value)

            self.db.commit()
            return True
        except Exception as e:
            print(f"Error actualizando campos del usuario: {e}")
            self.db.rollback()
            return False

    async def get_all_users(self) -> List[UserResponse]:
        """Obtener todos los usuarios (solo para desarrollo)"""
        try:
            users = (
                self.db.query(User)
                .options(joinedload(User.role))
                .all()
            )
            return [UserResponse.from_orm(user) for user in users]
        except Exception as e:
            print(f"Error obteniendo usuarios: {e}")
            return []

    async def delete_user(self, uid: str) -> bool:
        """Eliminar usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if user:
                self.db.delete(user)
                self.db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error eliminando usuario: {e}")
            self.db.rollback()
            return False
