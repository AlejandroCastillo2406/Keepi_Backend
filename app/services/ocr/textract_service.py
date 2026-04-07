import boto3
from fastapi import HTTPException

# Inicializa el cliente
textract_client = boto3.client('textract', region_name='us-east-1')

async def extract_text_from_document(file_bytes: bytes = None, s3_bucket: str = None, s3_key: str = None) -> str:
    """
    Extrae texto usando Bytes (para imágenes) o usando S3 (para PDFs de 1 página).
    """
    try:
        # Si nos mandan datos de S3, usamos el método para PDFs
        if s3_bucket and s3_key:
            response = textract_client.detect_document_text(
                Document={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
            )
        # Si no, usamos el método directo en memoria para imágenes
        elif file_bytes:
            response = textract_client.detect_document_text(
                Document={'Bytes': file_bytes}
            )
        else:
            raise ValueError("Debes proporcionar file_bytes o coordenadas de S3.")
            
        text_lines = []
        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                text_lines.append(block["Text"])
                
        return "\n".join(text_lines)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Textract: {str(e)}")