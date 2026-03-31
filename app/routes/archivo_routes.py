import os
import boto3
import mimetypes
from botocore.exceptions import ClientError
from fastapi import APIRouter, status, BackgroundTasks
from app.core.config import settings

router = APIRouter()

# Clientes de AWS
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

ses_client = boto3.client(
    "ses",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

async def enviar_email_con_visor(destinatario: str, url_s3: str):
    """Manda el correo con el link para visualizar"""
    SENDER = f"{settings.ses_from_name} <{settings.ses_from_email}>"
    SUBJECT = "Tu documento Keepi está listo para ver"
    
    BODY_HTML = f"""
    <html>
    <body style="font-family: sans-serif; text-align: center; padding: 40px;">
        <div style="max-width: 500px; margin: auto; background: white; padding: 30px; border-radius: 15px; border: 1px solid #eee; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
            <img src="https://raw.githubusercontent.com/AlejandroCastillo2406/Keepi_Front/master/assets/images/logo.png" style="height: 45px; margin-bottom: 20px;">
            <h2 style="color: #1e293b;">¡Hola!</h2>
            <p style="color: #64748b;">Tu documento ha sido procesado por <b>CALEX PC</b>. Haz clic abajo para visualizarlo:</p>
            <div style="margin: 30px 0;">
                <a href="{url_s3}" target="_blank" style="background-color: #E66A00; color: white; padding: 15px 25px; text-decoration: none; border-radius: 10px; font-weight: bold; display: inline-block;">Visualizar Documento</a>
            </div>
            <p style="color: #94a3b8; font-size: 11px;">Por seguridad, este enlace expirará pronto.</p>
        </div>
    </body>
    </html>
    """
    try:
        ses_client.send_email(
            Destination={'ToAddresses': [destinatario]},
            Message={
                'Body': {'Html': {'Charset': "UTF-8", 'Data': BODY_HTML}},
                'Subject': {'Charset': "UTF-8", 'Data': SUBJECT},
            },
            Source=SENDER,
        )
        print(f"✅ Email enviado con éxito a {destinatario}")
    except Exception as e:
        print(f"❌ Error al enviar email: {e}")

@router.get("/generar-acceso-s3-seguro")
async def generar_acceso_total_s3(
    file_key: str, 
    email_usuario_autorizado: str, 
    background_tasks: BackgroundTasks, 
    tiempo_min: int = 60
):
    """Genera el link de visualización directa de S3 y lo manda por correo"""
    try:
        # 1. Detectar el tipo de archivo (PDF, Imagen, etc.)
        content_type, _ = mimetypes.guess_type(file_key)
        # Si no se reconoce, ponemos uno por defecto para PDF
        if not content_type:
            content_type = "application/pdf"

        # 2. Generar la URL prefirmada del archivo FORZANDO LA VISUALIZACIÓN
        # Al añadir ResponseContentDisposition="inline", el navegador intenta abrirlo en vez de bajarlo
        url_s3_visor = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.aws_s3_bucket,
                "Key": file_key,
                "ResponseContentDisposition": "inline", # <-- AQUÍ ESTÁ LA MAGIA
                "ResponseContentType": content_type     # <-- INDICA AL NAVEGADOR EL FORMATO
            },
            ExpiresIn=tiempo_min * 60
        )

        # 3. Programar el envío del correo
        background_tasks.add_task(enviar_email_con_visor, email_usuario_autorizado, url_s3_visor)

        return {
            "status": "success",
            "message": f"Liga de visualización enviada a {email_usuario_autorizado}",
            "liga_enviada": url_s3_visor
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}