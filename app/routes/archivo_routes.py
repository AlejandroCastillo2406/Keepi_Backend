from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.core.security import require_doctor_user
from app.factories.archivo_factory import get_receta_archivo_procesamiento_service
from app.models.user import User
from app.services.almacenamiento.archivo_service import (
    RecetaArchivoProcesamientoService,
)

router = APIRouter()


@router.post("/extraer-texto")
async def extraer_texto_endpoint(
    file: UploadFile = File(...),
    current_doctor: User = Depends(require_doctor_user),
    svc: RecetaArchivoProcesamientoService = Depends(
        get_receta_archivo_procesamiento_service
    ),
):
    if not file:
        raise HTTPException(status_code=400, detail="No hay archivo.")
    try:
        file_bytes = await file.read()
        return await svc.extraer_texto_y_receta(
            file_bytes=file_bytes,
            content_type=file.content_type,
            filename=file.filename,
            doctor_email=current_doctor.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Receta no válida: No se detectó un número de cédula profesional clara.",
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generar-acceso-s3-seguro")
async def generar_acceso_total_s3(
    file_key: str,
    email_usuario_autorizado: str,
    background_tasks: BackgroundTasks,
    tiempo_min: int = 60,
    svc: RecetaArchivoProcesamientoService = Depends(
        get_receta_archivo_procesamiento_service
    ),
):
    del email_usuario_autorizado, background_tasks
    return svc.generar_url_presignada(file_key, tiempo_min)
