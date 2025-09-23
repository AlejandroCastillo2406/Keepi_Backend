"""
Alternativa de autenticación usando hashlib en caso de problemas con bcrypt
"""

import hashlib
import secrets

def hash_password_alternative(password: str) -> str:
    """Hash de contraseña usando hashlib como alternativa"""
    # Generar salt aleatorio
    salt = secrets.token_hex(16)
    # Hash de la contraseña con salt
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    # Retornar salt + hash como string
    return f"{salt}:{password_hash.hex()}"

def verify_password_alternative(password: str, hashed_password: str) -> bool:
    """Verificar contraseña usando hashlib como alternativa"""
    try:
        # Separar salt y hash
        salt, password_hash = hashed_password.split(':')
        # Hash la contraseña con el salt
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        # Comparar hashes
        return new_hash.hex() == password_hash
    except:
        return False

# Función para usar la alternativa si bcrypt falla
def get_password_hash_safe(password: str) -> str:
    """Hash de contraseña seguro con fallback"""
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    except:
        # Fallback a hashlib
        return hash_password_alternative(password)

def verify_password_safe(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña seguro con fallback"""
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(plain_password, hashed_password)
    except:
        # Fallback a hashlib
        return verify_password_alternative(plain_password, hashed_password)
