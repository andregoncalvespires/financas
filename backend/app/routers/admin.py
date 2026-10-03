"""Área de administração (só contagens e a liberação da IA do servidor). Só quem entra com o e-mail de ADMIN_EMAIL; sem ADMIN_EMAIL, ninguém."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import exigir_admin, get_db

router = APIRouter(prefix="/api/admin", dependencies=[Depends(exigir_admin)])


@router.get("/usuarios")
def usuarios(cur=Depends(get_db)):
    """Pessoas cadastradas com data de cadastro, último acesso e quantas contas e cartões ativos são delas (como donas)."""
    return cur.execute("SELECT * FROM admin_listar_usuarios()").fetchall()


class IaIn(BaseModel):
    liberada: bool


@router.post("/usuarios/{uid}/ia")
def liberar_ia(uid: UUID, body: IaIn, cur=Depends(get_db)):
    """Liga ou desliga a leitura por IA com a chave do SERVIDOR para uma pessoa."""
    ok = cur.execute("SELECT admin_definir_ia(%s, %s) AS ok", (str(uid), body.liberada)).fetchone()["ok"]
    if not ok:
        raise HTTPException(404, "pessoa não encontrada")
    return {"id": str(uid), "ia_servidor": body.liberada}
