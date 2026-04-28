import secrets
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.auth.jwt_payloads import access_token_claims_for_user
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT, ROLE_USER
from app.models.role import Role
from app.models.user import User, UserCreate, UserLogin, UserResponse, UserUpdate
from app.repositories.user_repository import UserRepository
from app.utils.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)


class UserService:

    def __init__(self, db: Session, user_repository: UserRepository | None = None):
        self.db = db
        self._users = user_repository or UserRepository(db)

    def role_id_by_name(self, name: str) -> int:
        rid = self._users.role_id_by_name(name)
        if rid is None:
            raise ValueError(f"Rol no encontrado en BD: {name}")
        return rid

    def get_user_orm_by_uid(self, uid: str) -> Optional[User]:
        return self._users.get_by_id_with_role(uid)

    async def get_user_by_uid(self, uid: str) -> Optional[UserResponse]:
        try:
            user = self._users.get_by_id_with_role(uid)
            if user:
                return UserResponse.from_orm(user)
            return None
        except Exception as e:
            print(f"Error obteniendo usuario: {e}")
            return None

    async def create_user(self, user_data: UserCreate) -> User:
        try:
            if self._users.email_exists(user_data.email):
                raise ValueError("El usuario con este email ya existe")

            role_key = user_data.role_name
            if role_key not in (ROLE_USER, ROLE_DOCTOR):
                raise ValueError("Solo puedes registrarte como usuario o como médico")
            rid = self.role_id_by_name(role_key)
            user = User(
                email=user_data.email,
                name=user_data.name,
                hashed_password=(
                    get_password_hash(user_data.password)
                    if user_data.password
                    else None
                ),
                role_id=rid,
                must_change_password=False,
            )

            self._users.add(user)
            self._users.commit()
            self._users.refresh(user)
            loaded = self._users.reload_with_role(user.id)
            if loaded is None:
                raise RuntimeError("No se pudo recargar el usuario creado")
            return loaded
        except Exception as e:
            print(f"Error creando usuario: {e}")
            self._users.rollback()
            raise

    async def create_patient_by_doctor(
        self,
        doctor: User,
        email: str,
        name: str,
    ) -> Tuple[User, str]:
        if doctor.role is None or doctor.role.name != ROLE_DOCTOR:
            raise PermissionError(
                "Solo un usuario con rol DOCTOR puede crear pacientes"
            )

        if self._users.email_exists(email):
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
        self._users.add(user)
        self._users.flush()
        self._users.commit()
        self._users.refresh(user)

        loaded = self._users.reload_with_role(user.id)
        if loaded is None:
            raise RuntimeError("No se pudo recargar el paciente creado")
        return loaded, plain

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        user = self._users.get_by_id_with_role(user_id)
        if user is None:
            raise ValueError("Usuario no encontrado")
        if not user.hashed_password:
            raise ValueError("Este usuario no tiene contraseña local")
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("La contraseña actual no es correcta")

        user.hashed_password = get_password_hash(new_password)
        user.must_change_password = False
        self._users.commit()
        self._users.refresh(user)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        try:
            user = self._users.get_by_email_with_role(email)
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
            self._users.commit()

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

    async def update_user(
        self, uid: str, user_data: UserUpdate
    ) -> Optional[UserResponse]:
        try:
            user = self._users.get_by_id_with_role(uid)
            if not user:
                return None

            update_data = user_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(user, field, value)

            self._users.commit()
            self._users.refresh(user)

            return UserResponse.from_orm(user)
        except Exception as e:
            print(f"Error actualizando usuario: {e}")
            self._users.rollback()
            return None

    async def update_user_fields(self, uid: str, fields: dict) -> bool:
        try:
            user = self._users.get_by_id_plain(uid)
            if not user:
                return False

            for field, value in fields.items():
                if hasattr(user, field):
                    setattr(user, field, value)

            self._users.commit()
            return True
        except Exception as e:
            print(f"Error actualizando campos del usuario: {e}")
            self._users.rollback()
            return False

    async def get_all_users(self) -> List[UserResponse]:
        try:
            users = self._users.list_all_with_role()
            return [UserResponse.from_orm(user) for user in users]
        except Exception as e:
            print(f"Error obteniendo usuarios: {e}")
            return []

    async def delete_user(self, uid: str) -> bool:
        try:
            user = self._users.get_by_id_plain(uid)
            if user:
                self._users.delete(user)
                return True
            return False
        except Exception as e:
            print(f"Error eliminando usuario: {e}")
            self._users.rollback()
            return False

    def set_refresh_token(self, user_id: str, refresh_token: str) -> Optional[User]:
        user = self._users.get_by_id_with_role(user_id)
        if not user:
            return None
        user.refresh_token = refresh_token
        self._users.commit()
        self._users.refresh(user)
        return user

    def list_patients_created_by_doctor(
        self, doctor_id, patient_role_id: int
    ) -> List[User]:
        return self._users.list_created_by_with_role(doctor_id, patient_role_id)

    def get_patient_if_owned_by_doctor(self, patient_id, doctor_id) -> Optional[User]:
        return self._users.get_patient_owned_by_doctor(patient_id, doctor_id)

    async def get_me_response(self, user_id: str) -> Optional[UserResponse]:
        user = self._users.get_by_id_with_role(user_id)
        if not user:
            return None
        return UserResponse.from_orm(user)

    def verify_registered_user_from_token(self, user_token: dict) -> dict:
        uid = user_token.get("uid") or user_token.get("sub")
        if not uid:
            raise ValueError("Token sin identificador de usuario")
        user = self._users.get_by_id_with_role(uid)
        if not user:
            raise ValueError("Usuario no encontrado")
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
        }
