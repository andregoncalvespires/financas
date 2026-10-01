from datetime import date, timedelta
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import Usuario, get_db, usuario_atual
from ..schemas import GerarRecorrenciasIn, RecorrenciaIn, RecorrenciaPatch, TransacaoIn, TransacaoPatch, TransferenciaIn
from ..servicos import (add_months, atualizar, criar_transacoes, dono_do_alvo, mes_intervalo,
                        resolver_favorecido_categoria)

router = APIRouter(prefix="/api")

SQL_TX = """
SELECT t.id, t.tipo, t.estado, t.valor_centavos, t.data_competencia, t.data_caixa, t.conta_id, t.plastico_id, t.fatura_id,
       t.forma_pagamento, t.categoria_id, t.favorecido_id, t.descricao, t.numero_parcela, t.total_parcelas, t.parcelamento_id,
       t.transferencia_id, t.origem, t.anexo_id, t.criado_por,
       c.nome AS conta_nome, pl.final AS plastico_final, pl.rotulo AS plastico_rotulo, k.nome AS cartao_nome,
       cat.nome AS categoria_nome, f.nome AS favorecido_nome, u.nome AS criado_por_nome,
       (SELECT c2.nome FROM transacao t2 JOIN conta c2 ON c2.id = t2.conta_id
         WHERE t.transferencia_id IS NOT NULL AND t2.transferencia_id = t.transferencia_id AND t2.id <> t.id) AS contraparte_nome
FROM transacao t
LEFT JOIN conta c ON c.id = t.conta_id
LEFT JOIN plastico pl ON pl.id = t.plastico_id
LEFT JOIN cartao k ON k.id = pl.cartao_id
LEFT JOIN categoria cat ON cat.id = t.categoria_id
LEFT JOIN favorecido f ON f.id = t.favorecido_id
LEFT JOIN usuario u ON u.id = t.criado_por
"""


def _filtros(de, ate, base, conta_id, plastico_id, cartao_id, fatura_id, estado, tipo, favorecido_id, categoria_id, busca):
    """Monta o WHERE comum à listagem e ao resumo (aliases: t transacao, f favorecido, cat categoria)."""
    col = "t.data_competencia" if base == "competencia" else "t.data_caixa"
    where, params = [], []
    for cond, val in ((f"{col} >= %s", de), (f"{col} <= %s", ate), ("t.conta_id = %s", conta_id), ("t.plastico_id = %s", plastico_id),
                      ("t.plastico_id IN (SELECT id FROM plastico WHERE cartao_id = %s)", cartao_id),
                      ("t.fatura_id = %s", fatura_id), ("t.estado = %s", estado), ("t.tipo = %s", tipo), ("t.favorecido_id = %s", favorecido_id)):
        if val is not None:
            where.append(cond)
            params.append(val)
    if categoria_id is not None:      # escolher uma categoria "pai" inclui as subcategorias
        where.append("t.categoria_id IN (SELECT id FROM categoria WHERE id = %s OR pai_id = %s)")
        params += [categoria_id, categoria_id]
    if busca and busca.strip():
        like = "%" + busca.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(t.descricao ILIKE %s OR f.nome ILIKE %s OR cat.nome ILIKE %s)")
        params += [like, like, like]
    return col, (" WHERE " + " AND ".join(where) if where else ""), params


@router.get("/transacoes")
def listar(de: date | None = None, ate: date | None = None, base: str = Query("competencia", pattern="^(competencia|caixa)$"),
           conta_id: str | None = None, plastico_id: str | None = None, cartao_id: str | None = None, fatura_id: str | None = None,
           estado: str | None = None, tipo: str | None = None, favorecido_id: str | None = None, categoria_id: str | None = None,
           busca: str | None = Query(None, max_length=100), limite: int = Query(200, le=1000), cur=Depends(get_db)):
    col, where, params = _filtros(de, ate, base, conta_id, plastico_id, cartao_id, fatura_id, estado, tipo, favorecido_id, categoria_id, busca)
    return cur.execute(SQL_TX + where + f" ORDER BY {col} DESC, t.criado_em DESC LIMIT %s", (*params, limite)).fetchall()


@router.get("/transacoes/resumo")
def resumo_filtrado(de: date | None = None, ate: date | None = None, base: str = Query("competencia", pattern="^(competencia|caixa)$"),
                    conta_id: str | None = None, plastico_id: str | None = None, cartao_id: str | None = None, fatura_id: str | None = None,
                    estado: str | None = None, tipo: str | None = None, favorecido_id: str | None = None, categoria_id: str | None = None,
                    busca: str | None = Query(None, max_length=100), cur=Depends(get_db)):
    """Totais da seleção (mesmos filtros da listagem), sem o limite de linhas, com a quebra por categoria e por favorecido."""
    _, where, params = _filtros(de, ate, base, conta_id, plastico_id, cartao_id, fatura_id, estado, tipo, favorecido_id, categoria_id, busca)
    de_ = ("FROM transacao t LEFT JOIN favorecido f ON f.id = t.favorecido_id LEFT JOIN categoria cat ON cat.id = t.categoria_id"
           + where + (" AND" if where else " WHERE") + " t.tipo IN ('despesa','receita')")
    tot = cur.execute("SELECT COALESCE(SUM(t.valor_centavos) FILTER (WHERE t.tipo = 'receita'), 0)::bigint AS receitas, "
                      "COALESCE(SUM(t.valor_centavos) FILTER (WHERE t.tipo = 'despesa'), 0)::bigint AS despesas, COUNT(*)::int AS quantidade " + de_, params).fetchone()
    cats = cur.execute("SELECT t.categoria_id AS id, COALESCE(cat.nome, 'Sem categoria') AS nome, SUM(t.valor_centavos)::bigint AS total, COUNT(*)::int AS itens "
                       + de_ + " GROUP BY t.categoria_id, cat.nome ORDER BY ABS(SUM(t.valor_centavos)) DESC LIMIT 50", params).fetchall()
    favs = cur.execute("SELECT t.favorecido_id AS id, COALESCE(f.nome, 'Sem favorecido') AS nome, SUM(t.valor_centavos)::bigint AS total, COUNT(*)::int AS itens "
                       + de_ + " GROUP BY t.favorecido_id, f.nome ORDER BY ABS(SUM(t.valor_centavos)) DESC LIMIT 50", params).fetchall()
    return {**tot, "por_categoria": cats, "por_favorecido": favs}


@router.post("/transacoes", status_code=201)
def criar(body: TransacaoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    criadas = criar_transacoes(cur, usuario.id, body)
    ids = [c["id"] for c in criadas]
    return cur.execute(SQL_TX + " WHERE t.id = ANY(%s) ORDER BY t.data_competencia", (ids,)).fetchall()


@router.patch("/transacoes/{tid}")
def alterar(tid: str, body: TransacaoPatch, cur=Depends(get_db)):
    t = cur.execute("SELECT * FROM transacao WHERE id = %s", (tid,)).fetchone()
    if not t:
        raise HTTPException(404, "lançamento não encontrado")
    if t["transferencia_id"] and body.estado:
        raise HTTPException(422, "confirme a transferência pelo botão de confirmar (as duas pontas mudam juntas)")
    if t["transferencia_id"] and (body.valor_centavos or body.data_caixa) and not (body.conta_id or body.data_competencia):
        if t["estado"] != "previsto":
            raise HTTPException(422, "só transferências previstas podem ser ajustadas; volte para previsto antes")
        n = cur.execute(f"UPDATE transacao SET valor_centavos = {SQL_NOVO_VALOR}, data_caixa = COALESCE(%(d)s, data_caixa), "
                        "data_competencia = COALESCE(%(d)s, data_competencia) WHERE transferencia_id = %(tf)s AND estado = 'previsto'",
                        {"v": body.valor_centavos, "d": body.data_caixa, "tf": t["transferencia_id"]}).rowcount
        if n != 2:
            raise HTTPException(403, "você não pode ajustar os dois lados desta transferência")
        return cur.execute(SQL_TX + " WHERE t.id = %s", (tid,)).fetchone()
    if t["tipo"] in ("transferencia", "pagamento_fatura") and (body.valor_centavos or body.conta_id or body.data_competencia):
        raise HTTPException(422, "exclua e recrie transferências e pagamentos de fatura para alterar valor, conta ou data")
    dono = dono_do_alvo(cur, t["conta_id"], t["plastico_id"])
    campos: dict = {}
    if body.valor_centavos is not None:
        campos["valor_centavos"] = abs(body.valor_centavos) * (1 if t["valor_centavos"] > 0 else -1)
    for k in ("descricao", "forma_pagamento", "estado", "data_caixa"):
        v = getattr(body, k)
        if v is not None:
            campos[k] = v
    if body.favorecido_id or body.favorecido_nome or body.categoria_id:
        fav, cat = resolver_favorecido_categoria(cur, dono, body.favorecido_id, body.favorecido_nome, body.categoria_id)
        if fav:
            campos["favorecido_id"] = fav
        if body.categoria_id:
            campos["categoria_id"] = cat
    if body.conta_id:
        if t["plastico_id"]:
            raise HTTPException(422, "compra em cartão não muda de conta")
        campos["conta_id"] = body.conta_id
    if body.data_competencia:
        if t["total_parcelas"]:
            raise HTTPException(422, "para mudar a data de uma compra parcelada, exclua e lance novamente")
        campos["data_competencia"] = body.data_competencia
        if t["plastico_id"]:
            f = cur.execute("SELECT * FROM fatura_para_compra(%s, %s)", (t["plastico_id"], body.data_competencia)).fetchone()
            campos.update(fatura_id=f["fatura_id"], data_caixa=f["data_vencimento"], data_compra=body.data_competencia)
        elif not body.data_caixa:
            campos["data_caixa"] = body.data_competencia
    atualizar(cur, "transacao", tid, campos)
    return cur.execute(SQL_TX + " WHERE t.id = %s", (tid,)).fetchone()


class ConfirmarIn(BaseModel):
    data_caixa: date | None = None          # data em que o dinheiro realmente se moveu (extrato); vazio mantém a prevista
    valor_centavos: int | None = Field(default=None, gt=0)   # valor real (ex.: conta de luz); vazio mantém o previsto


# o sinal de cada lançamento (despesa/saída negativo, receita/entrada positivo) é preservado ao trocar o valor
SQL_NOVO_VALOR = "CASE WHEN %(v)s::bigint IS NULL THEN valor_centavos WHEN valor_centavos < 0 THEN -%(v)s::bigint ELSE %(v)s::bigint END"


@router.post("/transacoes/{tid}/confirmar")
def confirmar(tid: str, body: ConfirmarIn | None = None, cur=Depends(get_db)):
    dia = body.data_caixa if body else None
    valor = body.valor_centavos if body else None
    if dia and dia > date.today() + timedelta(days=1):
        raise HTTPException(422, "a data de efetivação não pode estar no futuro")
    t = cur.execute("SELECT transferencia_id, plastico_id FROM transacao WHERE id = %s", (tid,)).fetchone()
    if (dia or valor) and t and t["plastico_id"]:
        raise HTTPException(422, "compras no cartão seguem a fatura; valor e data não podem ser alterados aqui")
    sets = f"estado = 'confirmado', data_caixa = COALESCE(%(d)s, data_caixa), valor_centavos = {SQL_NOVO_VALOR}"
    if t and t["transferencia_id"]:      # as duas pontas da transferência são confirmadas juntas
        n = cur.execute(f"UPDATE transacao SET {sets} WHERE transferencia_id = %(tf)s AND estado = 'previsto'",
                        {"d": dia, "v": valor, "tf": t["transferencia_id"]}).rowcount
        if n == 0:
            raise HTTPException(404, "lançamento previsto não encontrado")
        if n != 2:
            raise HTTPException(403, "você não pode confirmar os dois lados desta transferência")
        return cur.execute(SQL_TX + " WHERE t.id = %s", (tid,)).fetchone()
    r = cur.execute(f"UPDATE transacao SET {sets} WHERE id = %(id)s AND estado = 'previsto' RETURNING id",
                    {"d": dia, "v": valor, "id": tid}).fetchone()
    if not r:
        raise HTTPException(404, "lançamento previsto não encontrado")
    return cur.execute(SQL_TX + " WHERE t.id = %s", (tid,)).fetchone()


@router.post("/transacoes/{tid}/desfazer")
def desfazer(tid: str, cur=Depends(get_db)):
    """Desfaz a efetivação: confirmado -> previsto (mantém a data). Transferências voltam as duas pontas juntas."""
    t = cur.execute("SELECT id, tipo, estado, plastico_id, transferencia_id FROM transacao WHERE id = %s", (tid,)).fetchone()
    if not t:
        raise HTTPException(404, "lançamento não encontrado")
    if t["estado"] == "previsto":
        raise HTTPException(409, "este lançamento já está previsto")
    if t["estado"] == "conciliado":
        raise HTTPException(422, "lançamento conciliado: desfaça a conciliação antes")
    if t["plastico_id"]:
        raise HTTPException(422, "compras no cartão não têm efetivação: elas entram na fatura")
    if t["tipo"] == "pagamento_fatura":
        raise HTTPException(422, "para desfazer o pagamento de uma fatura, exclua o pagamento (a fatura é reaberta)")
    if t["transferencia_id"]:
        n = cur.execute("UPDATE transacao SET estado = 'previsto' WHERE transferencia_id = %s AND estado = 'confirmado'", (t["transferencia_id"],)).rowcount
        if n != 2:
            raise HTTPException(403, "você não pode desfazer os dois lados desta transferência")
    elif not cur.execute("UPDATE transacao SET estado = 'previsto' WHERE id = %s AND estado = 'confirmado' RETURNING id", (tid,)).fetchone():
        raise HTTPException(403, "sem permissão para alterar este lançamento")
    return cur.execute(SQL_TX + " WHERE t.id = %s", (tid,)).fetchone()


@router.delete("/transacoes/{tid}")
def excluir(tid: str, todo_parcelamento: bool = False, cur=Depends(get_db)):
    t = cur.execute("SELECT id, tipo, transferencia_id, parcelamento_id FROM transacao WHERE id = %s", (tid,)).fetchone()
    if not t:
        raise HTTPException(404, "lançamento não encontrado")
    if t["transferencia_id"]:
        n = cur.execute("DELETE FROM transacao WHERE transferencia_id = %s", (t["transferencia_id"],)).rowcount
        if n != 2:
            raise HTTPException(403, "você não pode excluir os dois lados desta transferência")
        return {"excluidos": n}
    if t["tipo"] == "pagamento_fatura":
        cur.execute("UPDATE fatura SET status = 'aberta' WHERE pagamento_transacao_id = %s", (tid,))
    if todo_parcelamento and t["parcelamento_id"]:
        n = cur.execute("DELETE FROM transacao WHERE parcelamento_id = %s AND estado <> 'conciliado'", (t["parcelamento_id"],)).rowcount
    else:
        n = cur.execute("DELETE FROM transacao WHERE id = %s", (tid,)).rowcount
    if not n:
        raise HTTPException(403, "sem permissão para excluir este lançamento")
    return {"excluidos": n}


@router.post("/transferencias", status_code=201)
def transferir(body: TransferenciaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    if body.conta_origem_id == body.conta_destino_id:
        raise HTTPException(422, "origem e destino devem ser diferentes")
    for cid in (body.conta_origem_id, body.conta_destino_id):
        c = cur.execute("SELECT inativa FROM conta WHERE id = %s", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "conta não encontrada")
        if c["inativa"]:
            raise HTTPException(422, "não é possível transferir de/para conta inativa")
    tid = uuid4()
    ids = []
    for conta, sinal in ((body.conta_origem_id, -1), (body.conta_destino_id, 1)):
        r = cur.execute(
            """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, conta_id, descricao, transferencia_id, origem)
               VALUES (%s,'transferencia',%s,%s,%s,%s,%s,%s,%s,'manual') RETURNING id""",
            (usuario.id, body.estado, sinal * body.valor_centavos, body.data, body.data, conta, body.descricao, tid)).fetchone()
        ids.append(r["id"])
    return {"transferencia_id": tid, "transacoes": cur.execute(SQL_TX + " WHERE t.id = ANY(%s) ORDER BY t.valor_centavos", (ids,)).fetchall()}


# ===== Recorrências (geram os lançamentos previstos de cada mês) =====
@router.get("/recorrencias")
def recorrencias(cur=Depends(get_db)):
    return cur.execute(
        """SELECT r.*, c.nome AS conta_nome, pl.final AS plastico_final, k.nome AS cartao_nome, f.nome AS favorecido_nome, cat.nome AS categoria_nome
           FROM recorrencia r LEFT JOIN conta c ON c.id = r.conta_id LEFT JOIN plastico pl ON pl.id = r.plastico_id
           LEFT JOIN cartao k ON k.id = pl.cartao_id LEFT JOIN favorecido f ON f.id = r.favorecido_id LEFT JOIN categoria cat ON cat.id = r.categoria_id
           ORDER BY r.ativa DESC, r.dia_mes""").fetchall()


@router.post("/recorrencias", status_code=201)
def criar_recorrencia(body: RecorrenciaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    dono = dono_do_alvo(cur, body.conta_id, body.plastico_id)
    fav, cat = resolver_favorecido_categoria(cur, dono, body.favorecido_id, body.favorecido_nome, body.categoria_id)
    return cur.execute(
        """INSERT INTO recorrencia(criado_por, conta_id, plastico_id, tipo, valor_centavos, dia_mes, forma_pagamento, categoria_id, favorecido_id, descricao, inicio, fim)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s, current_date),%s) RETURNING *""",
        (usuario.id, body.conta_id, body.plastico_id, body.tipo, body.valor_centavos, body.dia_mes, body.forma_pagamento, cat, fav,
         body.descricao, body.inicio, body.fim)).fetchone()


@router.patch("/recorrencias/{rid}")
def alterar_recorrencia(rid: str, body: RecorrenciaPatch, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Altera a recorrência para os próximos meses. Os previstos dela a partir do mês escolhido são refeitos com os dados novos;
    o que já foi confirmado não muda. Pausar (ativa=false) ou definir um fim remove os previstos que ficam de fora."""
    r = cur.execute("SELECT * FROM recorrencia WHERE id = %s", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "recorrência não encontrada")
    dono = dono_do_alvo(cur, r["conta_id"], r["plastico_id"])
    campos: dict = {k: getattr(body, k) for k in ("valor_centavos", "dia_mes", "descricao", "forma_pagamento", "ativa")}
    if body.limpar_fim:
        campos["fim"] = None
    elif body.fim is not None:
        campos["fim"] = body.fim
    if body.favorecido_id or body.favorecido_nome or body.categoria_id:
        fav, cat = resolver_favorecido_categoria(cur, dono, body.favorecido_id, body.favorecido_nome, body.categoria_id)
        if fav:
            campos["favorecido_id"] = fav
        if body.categoria_id:
            campos["categoria_id"] = cat
    if r["plastico_id"] and body.forma_pagamento:
        campos.pop("forma_pagamento")            # compra em cartão é sempre "cartão"
    nova = atualizar(cur, "recorrencia", rid, campos, nulos={"fim"} if body.limpar_fim else frozenset())
    ini = date.fromisoformat(body.a_partir_de + "-01") if body.a_partir_de else date.today().replace(day=1)
    meses = {m["mes"] for m in cur.execute(
        "SELECT DISTINCT date_trunc('month', data_competencia)::date AS mes FROM transacao WHERE recorrencia_id = %s AND estado = 'previsto' AND data_competencia >= %s", (rid, ini)).fetchall()}
    removidos = cur.execute("DELETE FROM transacao WHERE recorrencia_id = %s AND estado = 'previsto' AND data_competencia >= %s", (rid, ini)).rowcount
    refeitos = 0
    if nova["ativa"]:
        meses |= {ini}                    # refaz os meses que existiam e o mês de partida
        for m in sorted(meses):
            refeitos += gerar(GerarRecorrenciasIn(mes=m.strftime("%Y-%m")), cur, usuario)["criadas"]
    return {**nova, "previstos_removidos": removidos, "previstos_gerados": refeitos}


@router.delete("/recorrencias/{rid}")
def excluir_recorrencia(rid: str, cur=Depends(get_db)):
    if not cur.execute("DELETE FROM recorrencia WHERE id = %s RETURNING id", (rid,)).fetchone():
        raise HTTPException(404, "recorrência não encontrada")
    return {"ok": True}


@router.post("/recorrencias/gerar")
def gerar(body: GerarRecorrenciasIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Gera, como 'previsto', os lançamentos do mês para cada recorrência ativa (idempotente)."""
    ini, fim = mes_intervalo(body.mes)
    recs = cur.execute("SELECT * FROM recorrencia WHERE ativa AND inicio <= %s AND (fim IS NULL OR fim >= %s)", (fim, ini)).fetchall()
    criadas = 0
    for r in recs:
        data = date(ini.year, ini.month, min(r["dia_mes"], fim.day))
        if data < r["inicio"] or (r["fim"] and data > r["fim"]):
            continue
        if cur.execute("SELECT 1 FROM transacao WHERE recorrencia_id = %s AND data_competencia BETWEEN %s AND %s", (r["id"], ini, fim)).fetchone():
            continue
        b = TransacaoIn(tipo=r["tipo"], valor_centavos=r["valor_centavos"], data_competencia=data, conta_id=r["conta_id"],
                        plastico_id=r["plastico_id"], categoria_id=r["categoria_id"], favorecido_id=r["favorecido_id"],
                        descricao=r["descricao"], forma_pagamento=r["forma_pagamento"], estado="previsto", origem="recorrencia")
        try:
            with cur.connection.transaction():
                criar_transacoes(cur, usuario.id, b, recorrencia_id=r["id"])
            criadas += 1
        except (psycopg.errors.InsufficientPrivilege, psycopg.errors.UniqueViolation):
            continue
    return {"criadas": criadas}
