import os
import uuid
import re
import boto3
import mimetypes
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from app.core.config import settings
from app.services.ocr.textract_service import extract_text_from_document

router = APIRouter()

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

# ==========================================
# LÓGICA MEJORADA: BUSCADOR FLEXIBLE DE CÉDULA
# ==========================================
def procesar_receta_con_seguridad(texto: str):
    """
    Busca la cédula de forma más flexible para formatos del IMSS.
    """
    texto_min = texto.lower()
    
    # 1. VALIDACIÓN FLEXIBLE
    # Buscamos que exista la palabra 'cedula' Y que exista un número de al menos 6 dígitos
    tiene_palabra_cedula = re.search(r'c[eé]dula', texto_min)
    tiene_numero_cedula = re.search(r'\b\d{6,8}\b', texto_min) # Busca números de 6 a 8 dígitos

    if not (tiene_palabra_cedula and tiene_numero_cedula):
        return None

    # 2. PROCESO DE DESGLOSE
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    medicamentos_encontrados = []

    for i, linea in enumerate(lineas):
        l_low = linea.lower()
        
        if "cada" in l_low and ("hora" in l_low or "hr" in l_low):
            # Extraer Horas
            horas_match = re.search(r'cada\s+(\d+)', l_low)
            horas = horas_match.group(1) if horas_match else "No detectado"

            # Extraer Días
            dias_match = re.search(r'durante\s+(\d+)', l_low)
            dias = dias_match.group(1) if dias_match else "No detectado"

            # Vía de Administración
            via = None 
            if "vía de administración" in l_low:
                via_texto = linea.split("administración")[-1].strip().capitalize()
                if via_texto: via = via_texto
            elif i > 0 and "vía de" in lineas[i-1].lower():
                via_texto = lineas[i-1].split("administración")[-1].strip().capitalize()
                if via_texto: via = via_texto

            # Nombre del Medicamento (Lógica de salto para el IMSS)
            nombre_med = "No identificado"
            for j in range(i - 1, max(-1, i - 4), -1):
                candidato = lineas[j]
                candidato_low = candidato.lower()
                if any(x in candidato_low for x in ["vía de", "administración", "receta", "folio", "médico", "cédula", "curp"]):
                    continue
                if len(candidato) > 5:
                    nombre_med = re.sub(r'^\d+\s+', '', candidato).strip()
                    break
            
            medicamentos_encontrados.append({
                "medicamento": nombre_med,
                "cada_cuantas_horas": horas,
                "duracion_dias": dias,
                "via_administracion": via
            })

    return medicamentos_encontrados

# ==========================================
# LOS ENDPOINTS SE MANTIENEN IGUAL
# ==========================================
@router.post("/extraer-texto")
async def extraer_texto_endpoint(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No hay archivo.")
        
    try:
        content_type = file.content_type
        file_bytes = await file.read()
        texto_raw = ""
        
        if content_type in ["image/jpeg", "image/png"]:
            texto_raw = await extract_text_from_document(file_bytes=file_bytes)
        elif content_type == "application/pdf":
            temp_key = f"temp_ocr_{uuid.uuid4()}.pdf"
            s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=temp_key, Body=file_bytes, ContentType="application/pdf")
            texto_raw = await extract_text_from_document(s3_bucket=settings.aws_s3_bucket, s3_key=temp_key)
            s3_client.delete_object(Bucket=settings.aws_s3_bucket, Key=temp_key)
        else:
            raise HTTPException(status_code=400, detail="Formato no soportado.")

        resultados = procesar_receta_con_seguridad(texto_raw)
        
        if resultados is None:
            raise HTTPException(
                status_code=403, 
                detail="Receta no válida: No se detectó un número de cédula profesional clara."
            )
        
        return {
            "status": "success",
            "filename": file.filename,
            "recordatorios": resultados
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/generar-acceso-s3-seguro")
async def generar_acceso_total_s3(file_key: str, email_usuario_autorizado: str, background_tasks: BackgroundTasks, tiempo_min: int = 60):
    try:
        url = s3_client.generate_presigned_url("get_object", Params={"Bucket": settings.aws_s3_bucket, "Key": file_key, "ResponseContentDisposition": "inline"}, ExpiresIn=tiempo_min * 60)
        return {"status": "success", "url": url}
    except Exception as e:
        return {"status": "error", "detail": str(e)}