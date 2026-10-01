import hashlib
import secrets

from .config import settings


def gerar_codigo() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_codigo(email: str, codigo: str) -> str:
    return hashlib.sha256(f"{settings.pepper}:{email.lower()}:{codigo}".encode()).hexdigest()


def gerar_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(f"{settings.pepper}:tok:{token}".encode()).hexdigest()
