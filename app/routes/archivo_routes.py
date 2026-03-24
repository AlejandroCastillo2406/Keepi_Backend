from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.archivo_repository import ArchivoRepository
from app.services.almacenamiento.archivo_service import ArchivoService

router = APIRouter()


@router.post("/subir")
async def subir_archivo(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    usuario_id = user.id

    # 🔥 AQUÍ se crea correctamente
    repo = ArchivoRepository(db)
    service = ArchivoService(repo)

    return service.subir_archivo(file, usuario_id)


@router.get("/ver/{token}")
def ver_archivo(
    token: str,
    db: Session = Depends(get_db)
):
    repo = ArchivoRepository(db)
    service = ArchivoService(repo)

    ruta = service.obtener_archivo(token)

    if not ruta:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return FileResponse(
        ruta,
        headers={"Content-Disposition": "inline"}
    )