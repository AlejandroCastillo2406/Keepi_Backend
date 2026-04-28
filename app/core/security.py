from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.models.user import User
from app.repositories.user_repository import UserRepository

security = HTTPBearer(auto_error=False)

MUST_CHANGE_PASSWORD_DETAIL = {
    "code": "MUST_CHANGE_PASSWORD",
    "message": "Debes cambiar tu contraseña temporal antes de continuar.",
}


def _get_password_hash(password: str) -> str:
    try:
        from passlib.context import CryptContext

        return CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)
    except Exception:
        import hashlib
        import secrets

        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return f"{salt}:{h.hex()}"


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        from passlib.context import CryptContext

        return CryptContext(schemes=["bcrypt"], deprecated="auto").verify(plain, hashed)
    except Exception:
        try:
            import hashlib

            salt, password_hash = hashed.split(":", 1)
            new_hash = hashlib.pbkdf2_hmac(
                "sha256", plain.encode("utf-8"), salt.encode("utf-8"), 100000
            )
            return new_hash.hex() == password_hash
        except Exception:
            return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return _get_password_hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update(
        {
            "exp": datetime.utcnow()
            + timedelta(days=settings.refresh_token_expire_days),
            "type": "refresh",
        }
    )
    return jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload if payload.get("type") == "refresh" else None
    except JWTError:
        return None


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
            )
        return {
            "uid": user_id,
            "email": payload.get("email"),
            "name": payload.get("name", ""),
            "picture": payload.get("picture", ""),
            "role_id": payload.get("role_id"),
            "role_name": payload.get("role_name", ""),
            "must_change_password": bool(payload.get("must_change_password")),
        }
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
            )
        user = UserRepository(db).get_by_id_with_role(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado"
            )
        return user
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_no_temp_password_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MUST_CHANGE_PASSWORD_DETAIL,
        )
    return current_user


def require_no_temp_password_token(
    user_token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
) -> dict:
    uid = user_token.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        )
    user = UserRepository(db).get_by_id_with_role(uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado"
        )
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MUST_CHANGE_PASSWORD_DETAIL,
        )
    return user_token


def require_patient_user(
    current_user: User = Depends(require_no_temp_password_user),
) -> User:
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este recurso solo está disponible para pacientes.",
        )
    return current_user


def require_doctor_user(
    current_user: User = Depends(require_no_temp_password_user),
) -> User:

    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Este recurso solo está disponible para doctores.",
        )
    return current_user
