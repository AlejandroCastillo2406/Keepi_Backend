from app.models.user import User


def access_token_claims_for_user(user: User) -> dict:
    role_name = user.role.name if getattr(user, "role", None) is not None else ""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role_id": user.role_id,
        "role_name": role_name,
        "must_change_password": bool(user.must_change_password),
    }
