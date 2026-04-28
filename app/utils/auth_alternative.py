import hashlib
import secrets


def hash_password_alternative(password: str) -> str:

    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    )

    return f"{salt}:{password_hash.hex()}"


def verify_password_alternative(password: str, hashed_password: str) -> bool:
    try:

        salt, password_hash = hashed_password.split(":")

        new_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        )

        return new_hash.hex() == password_hash
    except:
        return False


def get_password_hash_safe(password: str) -> str:
    try:
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    except:

        return hash_password_alternative(password)


def verify_password_safe(plain_password: str, hashed_password: str) -> bool:
    try:
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(plain_password, hashed_password)
    except:

        return verify_password_alternative(plain_password, hashed_password)
