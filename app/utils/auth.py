from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.database import DatabaseConfig

# Security
security = HTTPBearer(auto_error=False)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verificar token de Firebase y retornar información del usuario"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Verificar token de Firebase
        token = credentials.credentials
        decoded_token = DatabaseConfig.verify_firebase_token(token)
        
        if decoded_token:
            return {
                "uid": decoded_token.get('uid'),
                "email": decoded_token.get('email'),
                "name": decoded_token.get('name', ''),
                "picture": decoded_token.get('picture', '')
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de Firebase inválido o expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error verificando token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error verificando credenciales de autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )
