from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_user
from app.models.user import User
from app.models.user_device_token import (
    RegisterDeviceTokenRequest,
    RegisterDeviceTokenResponse,
    UserDeviceToken,
)

router = APIRouter()


@router.post("/register", response_model=RegisterDeviceTokenResponse)
async def register_push_token(
    body: RegisterDeviceTokenRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    row = db.query(UserDeviceToken).filter(UserDeviceToken.token == body.token).first()
    if row is None:
        row = UserDeviceToken(
            user_id=current_user.id,
            token=body.token,
            platform=body.platform,
            is_active=True,
        )
        db.add(row)
    else:
        row.user_id = current_user.id
        row.platform = body.platform
        row.is_active = True
    db.commit()
    db.refresh(row)
    return RegisterDeviceTokenResponse(
        token=row.token,
        platform=row.platform,
        updated_at=row.updated_at,
    )

