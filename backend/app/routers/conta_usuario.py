"""Sobre o app (versão) e ciclo de vida da conta da pessoa: exportar tudo e excluir a conta com os dados."""
import io
import logging
import re
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import mailer
from ..config import settings
from ..db import sessao
from ..deps import COOKIE, Usuario, get_db, usuario_atual
from ..security import gerar_codigo, hash_codigo
from .auth import _ip
from .exportar import exportar

log = logging.getLogger("uvicorn.error.conta")
router = APIRouter(prefix="/api")
RAIZ = Path(__file__).resolve().parents[3]


class ExcluirIn(BaseModel):
    confirmacao: str
    codigo: str


def _ler(nome: str) -> str:
    try:
        return (RAIZ / nome).read_text(encoding="utf-8")
    except OSError:
        return ""


@router.get("/versao")
def versao():
    """Versão em uso e histórico (do CHANGELOG). Público: não expõe dados de ninguém."""
    atual = _ler("VERSION").strip() or "desconhecida"
    historico, item = [], None
    for linha in _ler("CHANGELOG.md").splitlines():
        m = re.match(r"^##\s+(\d+\.\d+\.\d+)(?:\s+[—-]\s+(\d{4}-\d{2}-\d{2}))?\s*$", linha)
        if m:
            item = {"versao": m.group(1), "data": m.group(2), "itens": []}
            historico.append(item)
        elif item is not None and linha.startswith("- "):
            item["itens"].append(linha[2:].strip())
    return {"versao": atual, "historico": historico[:15]}


@router.get("/exportar/completo")
def exportar_completo(cur=Depends(get_db)):
    """ZIP com a planilha de todos os lançamentos visíveis e os comprovantes."""
    planilha = exportar(date(2000, 1, 1), date(2100, 12, 31), "competencia", cur)
    base = Path(settings.dados_dir).resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("financas_completo.xlsx", planilha.body)
        for a in cur.execute("SELECT id, caminho FROM anexo").fetchall():
            arq = (base / a["caminho"]).resolve()
            if base in arq.parents and arq.is_file():
                z.write(arq, f"comprovantes/{a['id']}{arq.suffix}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="financas_completo_{date.today().isoformat()}.zip"'})


@router.get("/conta/exclusao")
def resumo_exclusao(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """O que será apagado, e quem perde acesso por causa disso (tudo respeitando o que a pessoa pode ver)."""
    me = usuario.id
    contas = cur.execute(
        """SELECT c.nome, COALESCE((SELECT array_agg(DISTINCT u.nome ORDER BY u.nome) FROM conta_acesso a JOIN usuario u ON u.id = a.usuario_id
                                     WHERE a.conta_id = c.id AND a.usuario_id <> %s), '{}') AS outros
           FROM conta c WHERE c.dono_id = %s ORDER BY c.nome""", (me, me)).fetchall()
    cartoes = cur.execute(
        """SELECT k.nome, COALESCE(array_agg(DISTINCT u.nome ORDER BY u.nome) FILTER (WHERE p.portador_id IS NOT NULL AND p.portador_id <> %s), '{}') AS outros
           FROM cartao k LEFT JOIN plastico p ON p.cartao_id = k.id LEFT JOIN usuario u ON u.id = p.portador_id
           WHERE k.dono_id = %s GROUP BY k.id, k.nome ORDER BY k.nome""", (me, me)).fetchall()
    n = cur.execute(
        """SELECT count(*)::int AS n FROM transacao t WHERE t.conta_id IN (SELECT id FROM conta WHERE dono_id = %s)
              OR t.plastico_id IN (SELECT p.id FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE k.dono_id = %s)""", (me, me)).fetchone()["n"]
    return {"contas": contas, "cartoes": cartoes, "lancamentos": n,
            "compartilhadas": [c["nome"] for c in contas if c["outros"]] + [k["nome"] for k in cartoes if k["outros"]]}


@router.post("/conta/exclusao/codigo", status_code=202)
def pedir_codigo(request: Request, bg: BackgroundTasks, usuario: Usuario = Depends(usuario_atual)):
    with sessao(usuario.id) as cur:
        email = cur.execute("SELECT email::text AS e FROM usuario WHERE id = %s", (usuario.id,)).fetchone()["e"]
    with sessao(None) as cur:
        codigo = gerar_codigo()
        ip = _ip(request)
        st = cur.execute("SELECT auth_registrar_otp(%s, %s, %s, %s) AS st", (email, hash_codigo(email, codigo), ip, settings.otp_validade_min)).fetchone()["st"]
    if st == "limite":
        raise HTTPException(429, "muitas solicitações; tente novamente mais tarde")
    bg.add_task(mailer.enviar, email, "Código para excluir sua conta",
                f"Seu código para EXCLUIR sua conta e todos os seus dados é {codigo}.\n"
                f"Ele vale por {settings.otp_validade_min} minutos. Se não foi você, não informe o código a ninguém e ignore este e-mail.")
    return {"detail": "código enviado para o seu e-mail"}


@router.delete("/conta")
def excluir_conta(body: ExcluirIn, response: Response, usuario: Usuario = Depends(usuario_atual)):
    if body.confirmacao.strip().upper() != "EXCLUIR":
        raise HTTPException(422, 'digite EXCLUIR para confirmar')
    with sessao(usuario.id) as cur:
        email = cur.execute("SELECT email::text AS e FROM usuario WHERE id = %s", (usuario.id,)).fetchone()["e"]
    with sessao(None) as cur:
        st = cur.execute("SELECT auth_verificar_otp(%s, %s) AS st", (email, hash_codigo(email, body.codigo.strip()))).fetchone()["st"]
    if st != "ok":
        raise HTTPException(400 if st == "invalido" else 429, "código inválido ou expirado" if st == "invalido" else "tentativas esgotadas; peça um novo código")
    with sessao(usuario.id) as cur:
        caminhos = cur.execute("SELECT excluir_minha_conta() AS c").fetchone()["c"] or []
    base = Path(settings.dados_dir).resolve()
    for c in caminhos:                       # arquivos de comprovantes que ninguém mais usa
        arq = (base / c).resolve()
        if base in arq.parents:
            arq.unlink(missing_ok=True)
    log.info("conta excluída (usuário %s): %d comprovante(s) removido(s)", usuario.id, len(caminhos))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
