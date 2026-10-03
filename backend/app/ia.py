"""Leitura por IA por pessoa: a chave do servidor só vale para quem o administrador liberou; cada pessoa pode ter a própria chave
(cifrada no banco, nunca devolvida à tela). Funções de apoio e rotas de /api/ia."""
import base64
import hashlib
import logging

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException

from .config import settings
from .db import sessao
from .deps import Usuario, eh_admin, get_db, usuario_atual
from .schemas import ChaveIaIn

log = logging.getLogger("uvicorn.error.ia")
router = APIRouter(prefix="/api")


def _fernet() -> Fernet:
    # chave de cifragem derivada do segredo do app (APP_PEPPER, gerado uma vez e guardado no volume de segredos)
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"{settings.pepper}:chave-ia".encode()).digest()))


def cifrar(chave: str) -> str:
    return _fernet().encrypt(chave.encode()).decode()


def decifrar(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None                       # segredo do app mudou: a pessoa precisa cadastrar a chave de novo


def servidor_configurado() -> bool:
    return bool(settings.gemini_api_key) or settings.gemini_mock


def modo(usuario: Usuario, cur=None) -> dict:
    """Como esta pessoa lê com IA agora: 'propria' (chave dela), 'servidor' (liberada pelo administrador) ou 'nenhum'.
    Inclui a chave decifrada (uso interno do servidor: NUNCA devolver na API)."""
    if cur is None:
        with sessao(usuario.id) as c:
            return modo(usuario, c)
    u = cur.execute("SELECT ia_servidor FROM usuario WHERE id = %s", (usuario.id,)).fetchone()
    k = cur.execute("SELECT chave_cifrada, final FROM usuario_ia WHERE usuario_id = %s", (usuario.id,)).fetchone()
    liberada = bool(u and u["ia_servidor"]) or eh_admin(usuario)
    chave = decifrar(k["chave_cifrada"]) if k else None
    if chave:
        return {"modo": "propria", "chave": chave, "final": k["final"], "servidor_liberado": liberada, "servidor_configurado": servidor_configurado()}
    ok = liberada and servidor_configurado()
    return {"modo": "servidor" if ok else "nenhum", "chave": None, "final": k["final"] if k else None,
            "servidor_liberado": liberada, "servidor_configurado": servidor_configurado()}


def publico(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "chave"}


def validar_chave(chave: str) -> None:
    """Pergunta ao Google se a chave é aceita (lista de modelos: não consome cota de leitura)."""
    if settings.gemini_mock:
        return
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 1}, headers={"x-goog-api-key": chave}, timeout=15)
    except httpx.HTTPError:
        raise HTTPException(502, "não consegui falar com o Google para testar a chave; tente de novo")
    if r.status_code in (400, 401, 403):
        raise HTTPException(400, "o Google não aceitou esta chave: confira se copiou inteira")
    if r.status_code >= 400:
        raise HTTPException(502, "o Google não conseguiu testar a chave agora; tente de novo")


@router.get("/ia")
def situacao(usuario: Usuario = Depends(usuario_atual)):
    return publico(modo(usuario))


@router.put("/ia/chave")
def salvar_chave(body: ChaveIaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    chave = body.chave.strip()
    validar_chave(chave)
    cur.execute(
        """INSERT INTO usuario_ia(usuario_id, chave_cifrada, final) VALUES (%s,%s,%s)
           ON CONFLICT (usuario_id) DO UPDATE SET chave_cifrada = EXCLUDED.chave_cifrada, final = EXCLUDED.final, atualizado_em = now()""",
        (usuario.id, cifrar(chave), chave[-4:]))
    return publico(modo(usuario, cur))


@router.delete("/ia/chave")
def remover_chave(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    cur.execute("DELETE FROM usuario_ia WHERE usuario_id = %s", (usuario.id,))
    return publico(modo(usuario, cur))
