"""Área de administração (somente leitura). Só quem entra com o e-mail de ADMIN_EMAIL; sem ADMIN_EMAIL, ninguém."""
from fastapi import APIRouter, Depends

from ..deps import exigir_admin, get_db

router = APIRouter(prefix="/api/admin", dependencies=[Depends(exigir_admin)])


@router.get("/usuarios")
def usuarios(cur=Depends(get_db)):
    """Pessoas cadastradas com data de cadastro, último acesso e quantas contas e cartões ativos são delas (como donas)."""
    return cur.execute("SELECT * FROM admin_listar_usuarios()").fetchall()
