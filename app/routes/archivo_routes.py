import os
import uuid
import re
import boto3
import mimetypes
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Depends
from app.core.config import settings
from app.services.ocr.textract_service import extract_text_from_document

# Importamos el guardián de seguridad y el modelo de usuario
from app.core.security import require_doctor_user
from app.models.user import User

router = APIRouter()

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)

def procesar_receta_con_seguridad(texto: str):
    """
    Desglosa la receta asegurando extraer solo el nombre de la medicina,
    la vía de administración en una palabra y los datos de tiempo.
    """
    texto_min = texto.lower()
    
    # 1. VALIDACIÓN FLEXIBLE DE CÉDULA
    tiene_palabra_cedula = re.search(r'c[eé]dula', texto_min)
    tiene_numero_cedula = re.search(r'\b\d{6,8}\b', texto_min)

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

            # --- Vía de Administración (Solo una palabra) ---
            via = None 
            linea_para_via = linea if "administraci" in l_low else (lineas[i-1] if i > 0 and "administraci" in lineas[i-1].lower() else "")
            
            if linea_para_via:
                match_via = re.search(r'administraci[oó]n\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)', linea_para_via, re.IGNORECASE)
                if match_via and match_via.group(1).strip():
                    via = match_via.group(1).strip().capitalize()

            # --- CORRECCIÓN: Solo el nombre de la medicina ---
            nombre_med = "No identificado"
            bloque_texto_medicamento = []
            
            for j in range(i - 1, max(-1, i - 8), -1):
                candidato = lineas[j].strip()
                candidato_low = candidato.lower()
                
                if len(candidato) < 4:
                    continue
                
                if "vía de administración" in candidato_low and j != i - 1 and j != i:
                    break
                    
                if any(x in candidato_low for x in ["fecha:", "primer nivel", "asegura tu", "esta receta", "folio"]):
                    break
                
                bloque_texto_medicamento.insert(0, candidato)
                
                if re.match(r'^\d{4,7}\s+(?!MG\b|ML\b|UI\b|G\b)[a-zA-Z]', candidato, re.IGNORECASE):
                    break

            if bloque_texto_medicamento:
                frase_completa = " ".join(bloque_texto_medicamento)
                
                # 1. Quitamos la clave numérica inicial
                frase_sin_clave = re.sub(r'^\d{4,7}\s+(?!MG\b|ML\b|UI\b|G\b)', '', frase_completa, flags=re.IGNORECASE).strip()
                
                # 2. Cortamos hasta el primer punto (ej. "SITAGLIPTINA. COMPRIMIDO...")
                nombre_corto = frase_sin_clave.split('.')[0].strip()
                
                # 3. Cortamos antes de cualquier forma farmacéutica para dejar solo el nombre
                palabras_corte = ["GRAGEA", "TABLETA", "COMPRIMIDO", "SOLUCION", "CAPSULA", "ENVASE", "MG", "ML", "UI", "SUSPENSION", "JARABE", "AMPOLLETA"]
                patron_corte = r'\b(?:' + '|'.join(palabras_corte) + r')\b'
                match_corte = re.search(patron_corte, nombre_corto, flags=re.IGNORECASE)
                
                if match_corte:
                    nombre_corto = nombre_corto[:match_corte.start()].strip()
                
                # Limpiamos el resultado final
                nombre_med = nombre_corto.upper() if nombre_corto else frase_sin_clave.split()[0].upper()
                
                # Evitar guiones colgantes al final (ej: "EZETIMIBA-")
                nombre_med = nombre_med.strip(" -")

            medicamentos_encontrados.append({
                "medicamento": nombre_med,
                "cada_cuantas_horas": horas,
                "duracion_dias": dias,
                "via_administracion": via
            })

    return medicamentos_encontrados


@router.post("/extraer-texto")
async def extraer_texto_endpoint(
    file: UploadFile = File(...),
    current_doctor: User = Depends(require_doctor_user)
):
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
        cedula_ok = resultados is not None
        if resultados is None:
            resultados = []

        return {
            "status": "success",
            "filename": file.filename,
            "doctor_autorizado": current_doctor.email,
            "raw_text": texto_raw,
            "recordatorios": resultados,
            "cedula_profesional_detectada": cedula_ok,
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