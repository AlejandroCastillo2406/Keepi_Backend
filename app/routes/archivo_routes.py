from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.services.almacenamiento.s3_service import S3Service
from app.core.security import get_current_user

router = APIRouter()


# 🔥 SUBIDA SIMPLE (SIN LOGIN - TEMPORAL)
@router.post("/subir-simple")
async def subir_archivo_simple(file: UploadFile = File(...)):
    try:
        service = S3Service()

        result = await service.upload_document(
            user_id="temp",  # 👈 usuario temporal
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type,
            folder="temp"
        )

        return {
            "url": result["signed_url"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 🔐 SUBIDA CON USUARIO (PRO)
@router.post("/subir")
async def subir_archivo(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        service = S3Service()

        result = await service.upload_document(
            user_id=str(user.id),
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type,
            folder="documents"
        )

        return {
            "url": result["signed_url"],
            "file_path": result["file_path"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))