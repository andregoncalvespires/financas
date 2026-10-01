from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import mailer
from ..config import settings
from ..deps import Usuario, get_db, usuario_atual
from ..schemas import CartaoIn, CartaoPatch, ConvitePortadorIn, PagarFaturaIn, PlasticoIn, PlasticoPatch
from ..servicos import atualizar, limitar_convites

router = APIRouter(prefix="/api")

SQL_CARTOES = """
SELECT k.id, k.nome, k.bandeira, k.dia_fechamento, k.dia_vencimento, k.dono_id, u.nome AS dono_nome, k.inativo,
       (k.dono_id = %(uid)s) AS sou_dono,
       CASE WHEN k.dono_id = %(uid)s THEN k.conta_pagamento_id END AS conta_pagamento_id,
       CASE WHEN k.dono_id = %(uid)s THEN k.limite_centavos END AS limite_centavos
FROM cartao k JOIN usuario u ON u.id = k.dono_id
"""

SQL_PLASTICOS = """
SELECT p.id, p.cartao_id, p.final, p.rotulo, p.tipo, p.principal, p.ativo, p.portador_id, pu.nome AS portador_nome
FROM plastico p LEFT JOIN usuario pu ON pu.id = p.portador_id
"""


def _cartoes(cur, uid, where="", params=None):
    p = {"uid": uid, **(params or {})}
    cartoes = cur.execute(SQL_CARTOES + where + " ORDER BY k.inativo, k.nome", p).fetchall()
    plasticos = cur.execute(SQL_PLASTICOS + " ORDER BY p.principal DESC, p.rotulo").fetchall()
    for c in cartoes:
        c["plasticos"] = [x for x in plasticos if x["cartao_id"] == c["id"]]
    return cartoes


@router.get("/cartoes")
def listar(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return _cartoes(cur, usuario.id)


@router.post("/cartoes", status_code=201)
def criar(body: CartaoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    if body.conta_pagamento_id and not cur.execute("SELECT pode_editar_conta(%s) AS ok", (body.conta_pagamento_id,)).fetchone()["ok"]:
        raise HTTPException(403, "sem permissão na conta de pagamento")
    r = cur.execute(
        """INSERT INTO cartao(dono_id, nome, bandeira, dia_fechamento, dia_vencimento, conta_pagamento_id, limite_centavos)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (usuario.id, body.nome, body.bandeira, body.dia_fechamento, body.dia_vencimento, body.conta_pagamento_id, body.limite_centavos)).fetchone()
    if body.final_principal:
        cur.execute("INSERT INTO plastico(cartao_id, final, rotulo, tipo, principal) VALUES (%s,%s,'Principal','plastico',true)", (r["id"], body.final_principal))
    return _cartoes(cur, usuario.id, " WHERE k.id = %(cid)s", {"cid": r["id"]})[0]


@router.patch("/cartoes/{cid}")
def alterar(cid: str, body: CartaoPatch, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    if body.conta_pagamento_id and not cur.execute("SELECT pode_editar_conta(%s) AS ok", (body.conta_pagamento_id,)).fetchone()["ok"]:
        raise HTTPException(403, "sem permissão na conta de pagamento")
    antes = cur.execute("SELECT dia_fechamento, dia_vencimento FROM cartao WHERE id = %s AND dono_id = %s", (cid, usuario.id)).fetchone()
    if not antes:
        raise HTTPException(404, "conta de cartão não encontrada ou você não é o dono")
    atualizar(cur, "cartao", cid, body.model_dump(), nulos=body.model_fields_set & {"conta_pagamento_id", "limite_centavos", "bandeira"})
    recalculadas = 0
    if (body.dia_fechamento and body.dia_fechamento != antes["dia_fechamento"]) or (body.dia_vencimento and body.dia_vencimento != antes["dia_vencimento"]):
        recalculadas = cur.execute("SELECT recalcular_faturas_abertas(%s) AS n", (cid,)).fetchone()["n"]
    out = _cartoes(cur, usuario.id, " WHERE k.id = %(cid)s", {"cid": cid})[0]
    out["faturas_recalculadas"] = recalculadas
    return out


@router.delete("/cartoes/{cid}")
def excluir(cid: str, com_historico: bool = False, cur=Depends(get_db)):
    """Sem compras: exclui. Com compras: só com com_historico=true (apaga também as compras); o usual é inativar."""
    if not cur.execute("SELECT dono_cartao(%s) AS ok", (cid,)).fetchone()["ok"]:
        raise HTTPException(404, "conta de cartão não encontrada ou você não é o dono")
    n = cur.execute("SELECT count(*)::int AS n FROM transacao t JOIN plastico p ON p.id = t.plastico_id WHERE p.cartao_id = %s", (cid,)).fetchone()["n"]
    if n and not com_historico:
        raise HTTPException(409, f"Esta conta de cartão tem {n} compra(s). Inative-a para preservar o histórico ou confirme a exclusão com todas as compras.")
    if n:
        apagadas = cur.execute("DELETE FROM transacao WHERE plastico_id IN (SELECT id FROM plastico WHERE cartao_id = %s)", (cid,)).rowcount
        if apagadas != n:
            raise HTTPException(403, "sem permissão para excluir todas as compras")
    if not cur.execute("DELETE FROM cartao WHERE id = %s RETURNING id", (cid,)).fetchone():
        raise HTTPException(404, "conta de cartão não encontrada")
    return {"ok": True, "compras_excluidas": n}


@router.post("/cartoes/{cid}/plasticos", status_code=201)
def criar_plastico(cid: str, body: PlasticoIn, cur=Depends(get_db)):
    if not cur.execute("SELECT dono_cartao(%s) AS ok", (cid,)).fetchone()["ok"]:
        raise HTTPException(404, "conta de cartão não encontrada ou você não é o dono")
    return cur.execute(
        "INSERT INTO plastico(cartao_id, final, rotulo, tipo, principal) VALUES (%s,%s,%s,%s,false) RETURNING id, cartao_id, final, rotulo, tipo, principal, ativo, portador_id",
        (cid, body.final, body.rotulo, body.tipo)).fetchone()


def _plastico_do_dono(cur, pid):
    p = cur.execute("SELECT p.* FROM plastico p WHERE p.id = %s AND dono_cartao(p.cartao_id)", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "cartão não encontrado ou você não é o dono")
    return p


@router.patch("/plasticos/{pid}")
def alterar_plastico(pid: str, body: PlasticoPatch, cur=Depends(get_db)):
    p = _plastico_do_dono(cur, pid)
    dados = body.model_dump(exclude={"principal"})
    tipo = body.tipo or p["tipo"]
    if p["principal"]:
        if body.principal is False:
            raise HTTPException(422, "para trocar o principal, marque outro cartão como principal")
        if tipo != "plastico":
            raise HTTPException(422, "o cartão principal é sempre do tipo Plástico")
        if body.ativo is False:
            raise HTTPException(422, "o cartão principal não pode ser inativado")
    if body.principal and not p["principal"]:
        if tipo != "plastico":
            raise HTTPException(422, "só um cartão do tipo Plástico pode ser o principal")
        if body.ativo is False or (not p["ativo"] and body.ativo is not True):
            raise HTTPException(422, "reative o cartão antes de torná-lo principal")
        cur.execute("UPDATE plastico SET principal = false WHERE cartao_id = %s AND principal", (p["cartao_id"],))
        dados["principal"] = True
    atualizar(cur, "plastico", pid, dados)
    return cur.execute(SQL_PLASTICOS + " WHERE p.id = %s", (pid,)).fetchone()


@router.delete("/plasticos/{pid}")
def excluir_plastico(pid: str, cur=Depends(get_db)):
    p = _plastico_do_dono(cur, pid)
    if p["principal"]:
        raise HTTPException(422, "o cartão principal não pode ser excluído: defina outro como principal ou exclua a conta de cartão")
    n = cur.execute("SELECT count(*)::int AS n FROM transacao WHERE plastico_id = %s", (pid,)).fetchone()["n"]
    if n:
        raise HTTPException(409, f"Este cartão tem {n} compra(s). Inative-o para preservar o histórico.")
    cur.execute("DELETE FROM plastico WHERE id = %s", (pid,))
    return {"ok": True}


@router.delete("/plasticos/{pid}/portador")
def remover_portador(pid: str, cur=Depends(get_db)):
    r = cur.execute("UPDATE plastico SET portador_id = NULL WHERE id = %s RETURNING id", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "plástico não encontrado ou você não é o dono")
    return {"ok": True}


@router.post("/plasticos/{pid}/convites", status_code=201)
def convidar_portador(pid: str, body: ConvitePortadorIn, bg: BackgroundTasks, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    p = cur.execute("SELECT p.final, p.portador_id, k.nome FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE p.id = %s AND k.dono_id = %s",
                    (pid, usuario.id)).fetchone()
    if not p:
        raise HTTPException(404, "plástico não encontrado ou você não é o dono")
    if p["portador_id"]:
        raise HTTPException(409, "este plástico já tem portador")
    email = body.email.lower()
    if email == usuario.email.lower():
        raise HTTPException(422, "você é o dono; o portador deve ser outra pessoa")
    limitar_convites(cur, usuario.id)
    desc = f"Cartão {p['nome']} (final {p['final']})"
    r = cur.execute("INSERT INTO convite(tipo, plastico_id, email, descricao, criado_por) VALUES ('portador',%s,%s,%s,%s) RETURNING id",
                    (pid, email, desc, usuario.id)).fetchone()
    bg.add_task(mailer.enviar, email, f"{usuario.nome} vinculou um cartão adicional a você",
                f"{usuario.nome} convidou você para registrar as compras do {desc}.\n"
                f"Entre em {settings.app_url} com este e-mail e aceite o convite. Você verá apenas as suas próprias compras.")
    return {"id": r["id"]}


@router.get("/cartoes/{cid}/faturas")
def faturas(cid: str, cur=Depends(get_db)):
    if not cur.execute("SELECT dono_cartao(%s) AS ok", (cid,)).fetchone()["ok"]:
        raise HTTPException(404, "cartão não encontrado ou você não é o dono")
    cur.execute("SELECT limpar_faturas_vazias(%s)", (cid,))       # tira da lista as faturas abertas e vazias que ficaram de exclusões antigas
    fats = cur.execute(
        """SELECT f.id, f.mes_referencia, f.data_fechamento, f.data_vencimento, f.status, f.pagamento_transacao_id,
                  COALESCE(SUM(t.valor_centavos), 0)::bigint AS total, COUNT(t.id)::int AS itens
           FROM fatura f LEFT JOIN transacao t ON t.fatura_id = f.id WHERE f.cartao_id = %s
           GROUP BY f.id ORDER BY f.data_vencimento DESC LIMIT 18""", (cid,)).fetchall()
    quebra = cur.execute(
        """SELECT t.fatura_id, p.id AS plastico_id, p.final, p.rotulo, pu.nome AS portador_nome, SUM(t.valor_centavos)::bigint AS total
           FROM transacao t JOIN plastico p ON p.id = t.plastico_id LEFT JOIN usuario pu ON pu.id = p.portador_id
           WHERE p.cartao_id = %s GROUP BY t.fatura_id, p.id, pu.nome""", (cid,)).fetchall()
    for f in fats:
        f["por_plastico"] = [q for q in quebra if q["fatura_id"] == f["id"]]
    return fats


@router.post("/faturas/{fid}/pagar")
def pagar(fid: str, body: PagarFaturaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    f = cur.execute("SELECT f.id, f.status, f.data_vencimento, k.nome FROM fatura f JOIN cartao k ON k.id = f.cartao_id WHERE f.id = %s", (fid,)).fetchone()
    if not f:
        raise HTTPException(404, "fatura não encontrada ou você não é o dono")
    if f["status"] == "paga":
        raise HTTPException(409, "fatura já paga")
    total = cur.execute("SELECT COALESCE(SUM(valor_centavos),0)::bigint AS t FROM transacao WHERE fatura_id = %s", (fid,)).fetchone()["t"]
    valor = body.valor_centavos or -total
    if valor <= 0:
        raise HTTPException(422, "fatura sem valor a pagar")
    dia = body.data or date.today()
    tx = cur.execute(
        """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, conta_id, forma_pagamento, descricao, origem)
           VALUES (%s,'pagamento_fatura','confirmado',%s,%s,%s,%s,'outro',%s,'manual') RETURNING id""",
        (usuario.id, -valor, dia, dia, body.conta_id, f"Fatura {f['nome']} venc. {f['data_vencimento'].strftime('%d/%m/%Y')}")).fetchone()
    cur.execute("UPDATE fatura SET status = 'paga', pagamento_transacao_id = %s WHERE id = %s", (tx["id"], fid))
    return {"ok": True, "transacao_id": tx["id"], "valor_centavos": valor}


@router.get("/portador/meus-gastos")
def meus_gastos(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Visão do portador: só o que ele mesmo gastou nos plásticos vinculados a ele (nunca o total da fatura nem o saldo do dono)."""
    plast = cur.execute(
        """SELECT p.id AS plastico_id, p.final, p.rotulo, k.nome AS cartao_nome, u.nome AS dono_nome
           FROM plastico p JOIN cartao k ON k.id = p.cartao_id JOIN usuario u ON u.id = k.dono_id
           WHERE p.portador_id = %s AND p.ativo ORDER BY k.nome""", (usuario.id,)).fetchall()
    for p in plast:
        atual = cur.execute("SELECT * FROM fatura_para_compra(%s, current_date)", (p["plastico_id"],)).fetchone()
        p["vencimento_atual"] = atual["data_vencimento"]
        p["faturas"] = cur.execute(
            """SELECT data_caixa AS vencimento, SUM(valor_centavos)::bigint AS total, COUNT(*)::int AS itens
               FROM transacao WHERE plastico_id = %s GROUP BY data_caixa ORDER BY data_caixa DESC LIMIT 12""", (p["plastico_id"],)).fetchall()
    return plast
