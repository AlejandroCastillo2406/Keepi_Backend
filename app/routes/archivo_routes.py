from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter()

@router.post("/subir")
async def subir_archivo(file: UploadFile = File(...)):
    service = router.service

    usuario_id = 1  # ⚠️ luego cámbialo por JWT real

    token = service.subir_archivo(file, usuario_id)

    return {
        "mensaje": "Archivo subido",
        "link": f"/api/v1/archivos/ver/{token}"
    }


@router.get("/ver/{token}")
def ver_archivo(token: str):
    service = router.service

    usuario_id = 1  # ⚠️ luego cámbialo por JWT real

    ruta, error = service.validar_archivo(token, usuario_id)

    if error:
        return {"error": error}

    return FileResponse(ruta)