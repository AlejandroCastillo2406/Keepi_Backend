from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.almacenamiento.cloud_storage_setup_service import (
    CloudStorageSetupService,
)


def get_cloud_storage_setup_service(
    db: Session = Depends(get_db),
) -> CloudStorageSetupService:
    return CloudStorageSetupService(db)
