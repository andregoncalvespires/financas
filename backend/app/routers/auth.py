import logging
import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from .. import mailer
from ..config import settings
from ..db import sessao
from ..deps import COOKIE, Usuario, eh_admin, get_db, usuario_atual
from ..schemas import PerfilIn, SolicitarIn, VerificarIn
from ..security import gerar_codigo, gerar_token, hash_codigo, hash_token

log = logging.getLogger("uvicorn.error.auth")

router = APIRouter(prefix="/api")


def _ip(request: Request) -> str | None:
    return (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else None)


@router.post("/auth/solicitar", status_code=202)
def solicitar(body: SolicitarIn, request: Request, bg: BackgroundTasks):
    email = body.email.lower()
    with sessao(None) as cur:   # quem prova ter o e-mail (recebendo o código) entra; a conta é criada no primeiro acesso
        codigo = gerar_codigo()
        st = cur.execute("SELECT auth_registrar_otp(%s, %s, %s, %s) AS st",
                         (email, hash_codigo(email, codigo), _ip(request), settings.otp_validade_min)).fetchone()["st"]
    log.info("código solicitado para %s: %s", email, st)
    if st == "ok":
        bg.add_task(mailer.enviar, email, "Seu código de acesso",
                    f"Seu código de acesso é {codigo}.\nEle vale por {settings.otp_validade_min} minutos. "
                    f"Se não foi você, ignore este e-mail.")
    elif st == "limite":
        raise HTTPException(429, "muitas solicitações; tente novamente mais tarde")
    return {"detail": "um código foi enviado para o e-mail informado"}


@router.post("/auth/verificar")
def verificar(body: VerificarIn, request: Request, response: Response, bg: BackgroundTasks):
    email = body.email.lower()
    with sessao(None) as cur:
        st = cur.execute("SELECT auth_verificar_otp(%s, %s) AS st", (email, hash_codigo(email, body.codigo))).fetchone()["st"]
    if st != "ok":
        raise HTTPException(400 if st == "invalido" else 429, "código inválido ou expirado" if st == "invalido" else "tentativas esgotadas; peça um novo código")
    with sessao(None) as cur:
        existia = cur.execute("SELECT auth_usuario_existe(%s) AS e", (email,)).fetchone()["e"]
        uid = cur.execute("SELECT auth_upsert_usuario(%s, %s, %s) AS id",
                          (email, email.split("@")[0].replace(".", " ").title(), True)).fetchone()["id"]
        token = gerar_token()
        cur.execute("SELECT auth_criar_dispositivo(%s, %s, %s)", (uid, hash_token(token), body.dispositivo))
    if not existia and settings.admin_email:   # avisa o administrador (ADMIN_EMAIL) de cada conta nova; sem ADMIN_EMAIL, não envia
        quando = datetime.now().strftime("%d/%m/%Y %H:%M")
        bg.add_task(mailer.enviar, settings.admin_email, "Finanças: novo usuário cadastrado",
                    f"Uma nova conta foi criada no Finanças.\n\nE-mail: {email}\nQuando: {quando}\n")
    response.set_cookie(COOKIE, token, max_age=365 * 24 * 3600, httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return {"token": token, "email": email}


@router.post("/auth/sair")
def sair(response: Response, usuario: Usuario = Depends(usuario_atual)):
    with sessao(usuario.id) as cur:
        cur.execute("UPDATE dispositivo SET revogado_em = now() WHERE id = %s", (usuario.dispositivo_id,))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/eu")
def eu(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    r = cur.execute("SELECT id, email::text AS email, nome, config FROM usuario WHERE id = %s", (usuario.id,)).fetchone()
    return {**r, "admin": eh_admin(usuario)}


@router.patch("/eu")
def atualizar_eu(body: PerfilIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    if body.nome:
        cur.execute("UPDATE usuario SET nome = %s WHERE id = %s", (body.nome, usuario.id))
    if body.config is not None:
        cur.execute("UPDATE usuario SET config = config || %s::jsonb WHERE id = %s", (json.dumps(body.config), usuario.id))
    r = cur.execute("SELECT id, email::text AS email, nome, config FROM usuario WHERE id = %s", (usuario.id,)).fetchone()
    return {**r, "admin": eh_admin(usuario)}


@router.get("/dispositivos")
def dispositivos(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    rows = cur.execute("SELECT id, nome, criado_em, ultimo_uso FROM dispositivo WHERE revogado_em IS NULL ORDER BY ultimo_uso DESC").fetchall()
    for r in rows:
        r["atual"] = r["id"] == usuario.dispositivo_id
    return rows


@router.delete("/dispositivos/{did}")
def revogar(did: str, cur=Depends(get_db)):
    r = cur.execute("UPDATE dispositivo SET revogado_em = now() WHERE id = %s AND revogado_em IS NULL RETURNING id", (did,)).fetchone()
    if not r:
        raise HTTPException(404, "dispositivo não encontrado")
    return {"ok": True}
