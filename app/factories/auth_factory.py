from fastapi import Depends

from app.core.security import verify_token


def get_current_user_token(token: dict = Depends(verify_token)) -> dict:
    return token
