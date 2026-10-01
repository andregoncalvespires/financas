from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from .config import settings
from .db import sessao
from .security import hash_token

COOKIE = "fin_dev"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Usuario:
    id: UUID
    email: str
    nome: str
    dispositivo_id: UUID


def usuario_atual(request: Request) -> Usuario:
    token = None
    via_cookie = False
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    else:
        token = request.cookies.get(COOKIE)
        via_cookie = True
    if not token:
        raise HTTPException(401, "não autenticado")
    # Defesa contra CSRF: com cookie, escritas exigem um cabeçalho que um formulário externo não consegue enviar.
    if via_cookie and request.method not in METODOS_SEGUROS and request.headers.get("x-fin") != "1":
        raise HTTPException(403, "cabeçalho X-Fin ausente")
    with sessao(None) as cur:
        r = cur.execute("SELECT * FROM auth_validar_dispositivo(%s, %s)",
                        (hash_token(token), settings.dispositivo_idle_dias)).fetchone()
    if not r or r["usuario_id"] is None:
        raise HTTPException(401, "sessão inválida ou revogada")
    return Usuario(id=r["usuario_id"], email=r["email"], nome=r["nome"], dispositivo_id=r["dispositivo_id"])


def get_db(usuario: Usuario = Depends(usuario_atual)):
    with sessao(usuario.id) as cur:
        yield cur
