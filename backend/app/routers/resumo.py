from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..servicos import mes_intervalo
from .contas import SQL_CONTAS

router = APIRouter(prefix="/api")


@router.get("/saldo-disponivel")
def saldo_disponivel(ate: date | None = None, cur=Depends(get_db)):
    """Saldo que sobra de verdade: saldo atual menos o que já está comprometido até a data (previstos e faturas de cartão).
    Sem subdivisões manuais: tudo é calculado a partir dos lançamentos previstos."""
    ate = min(ate, date.today() + timedelta(days=400)) if ate else date.today() + timedelta(days=30)
    contas = cur.execute(SQL_CONTAS + " WHERE NOT c.inativa ORDER BY c.nome").fetchall()
    previstos = cur.execute(
        """SELECT t.conta_id, COALESCE(t.forma_pagamento, 'outro') AS forma,
                  COALESCE(SUM(t.valor_centavos) FILTER (WHERE t.valor_centavos < 0), 0)::bigint AS saidas,
                  COALESCE(SUM(t.valor_centavos) FILTER (WHERE t.valor_centavos > 0), 0)::bigint AS entradas
           FROM transacao t WHERE t.conta_id IS NOT NULL AND t.estado = 'previsto' AND t.tipo <> 'transferencia' AND t.data_caixa <= %s GROUP BY 1, 2""", (ate,)).fetchall()
    # transferências previstas movem o disponível entre contas (a origem reserva o valor, o destino o recebe) sem ser pagar/receber
    transf = {r["conta_id"]: r["v"] for r in cur.execute(
        "SELECT conta_id, SUM(valor_centavos)::bigint AS v FROM transacao WHERE estado = 'previsto' AND tipo = 'transferencia' AND data_caixa <= %s GROUP BY 1", (ate,)).fetchall()}
    faturas = cur.execute(
        """SELECT k.conta_pagamento_id AS conta_id, f.id AS fatura_id, k.nome AS cartao_nome, f.data_vencimento,
                  COALESCE(SUM(t.valor_centavos), 0)::bigint AS total
           FROM fatura f JOIN cartao k ON k.id = f.cartao_id JOIN transacao t ON t.fatura_id = f.id
           WHERE f.status <> 'paga' AND f.data_vencimento <= %s AND k.conta_pagamento_id IS NOT NULL
           GROUP BY f.id, k.id ORDER BY f.data_vencimento""", (ate,)).fetchall()
    geral = {"saldo_atual": 0, "saidas_previstas": 0, "faturas": 0, "entradas_previstas": 0}
    for c in contas:
        pv = [p for p in previstos if p["conta_id"] == c["id"]]
        fs = [f for f in faturas if f["conta_id"] == c["id"]]
        c["por_forma"] = {p["forma"]: p["saidas"] for p in pv if p["saidas"]}
        c["saidas_previstas"] = sum(p["saidas"] for p in pv)
        c["entradas_previstas"] = sum(p["entradas"] for p in pv)
        c["faturas"] = [{k: v for k, v in f.items() if k != "conta_id"} for f in fs]
        c["faturas_total"] = sum(f["total"] for f in fs)
        c["transferencias_previstas"] = int(transf.get(c["id"], 0))
        c["livre"] = c["saldo_atual"] + c["saidas_previstas"] + c["faturas_total"] + c["transferencias_previstas"]
        c["projetado"] = c["livre"] + c["entradas_previstas"]
        geral["saldo_atual"] += c["saldo_atual"]
        geral["saidas_previstas"] += c["saidas_previstas"]
        geral["faturas"] += c["faturas_total"]
        geral["entradas_previstas"] += c["entradas_previstas"]
    geral["livre"] = sum(c["livre"] for c in contas)
    geral["projetado"] = geral["livre"] + geral["entradas_previstas"]
    return {"ate": ate, "contas": contas, "geral": geral}


@router.get("/resumo/mensal")
def resumo_mensal(mes: str = Query(pattern=r"^\d{4}-\d{2}$"), cur=Depends(get_db)):
    ini, fim = mes_intervalo(mes)
    rows = cur.execute(
        """SELECT t.tipo, COALESCE(g.nome, 'Sem categoria') AS grupo, COALESCE(c.nome, 'Sem categoria') AS categoria,
                  SUM(t.valor_centavos)::bigint AS total,
                  COALESCE(SUM(t.valor_centavos) FILTER (WHERE t.estado = 'previsto'), 0)::bigint AS previsto
           FROM transacao t LEFT JOIN categoria c ON c.id = t.categoria_id LEFT JOIN categoria g ON g.id = c.pai_id
           WHERE t.tipo IN ('despesa', 'receita') AND t.data_competencia BETWEEN %s AND %s
           GROUP BY 1, 2, 3 ORDER BY 1, 4""", (ini, fim)).fetchall()
    out = {"mes": mes, "receitas": 0, "despesas": 0, "grupos": []}
    grupos: dict[str, dict] = {}
    for r in rows:
        if r["tipo"] == "receita":
            out["receitas"] += r["total"]
            continue
        out["despesas"] += r["total"]
        g = grupos.setdefault(r["grupo"], {"grupo": r["grupo"], "total": 0, "previsto": 0, "categorias": []})
        g["total"] += r["total"]
        g["previsto"] += r["previsto"]
        g["categorias"].append({"categoria": r["categoria"], "total": r["total"], "previsto": r["previsto"]})
    out["grupos"] = sorted(grupos.values(), key=lambda g: g["total"])
    out["resultado"] = out["receitas"] + out["despesas"]
    return out
