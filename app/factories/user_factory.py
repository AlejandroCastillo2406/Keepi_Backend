from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.usuarios.push_token_service import PushTokenService
from app.services.usuarios.user_config_service import UserConfigService
from app.services.usuarios.user_service import UserService


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


def get_user_config_service(db: Session = Depends(get_db)) -> UserConfigService:
    return UserConfigService(db)


def get_push_token_service(db: Session = Depends(get_db)) -> PushTokenService:
    return PushTokenService(db)
