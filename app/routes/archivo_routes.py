from fastapi import APIRouter
import boto3
from app.core.config import settings

router = APIRouter()

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

@router.get("/link-temporal")
def generar_link_temporal(file_key: str, tiempo_expiracion_minutos: int):

    tiempo_en_segundos = tiempo_expiracion_minutos * 60

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.aws_s3_bucket,  # ← CORREGIDO
            "Key": file_key
        },
        ExpiresIn=tiempo_en_segundos
    )

    return {
        "url": url,
        "expira_en_minutos": tiempo_expiracion_minutos
    }