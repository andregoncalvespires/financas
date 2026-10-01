from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from ..deps import get_db

router = APIRouter(prefix="/api")


@router.get("/lembretes")
def lembretes(dias: int = Query(7, ge=0, le=90), cur=Depends(get_db)):
    """O que ainda precisa acontecer: lançamentos previstos das contas e faturas de cartão em aberto, até hoje + N dias,
    mais tudo o que já está atrasado. Cada pessoa vê apenas o que as suas permissões permitem."""
    hoje = date.today()
    ate = hoje + timedelta(days=dias)
    itens = []
    for r in cur.execute(
            """SELECT t.id, t.tipo AS natureza, t.valor_centavos, t.data_caixa AS data, t.descricao, f.nome AS favorecido_nome,
                      c.nome AS conta_nome, cat.nome AS categoria_nome
               FROM transacao t JOIN conta c ON c.id = t.conta_id
               LEFT JOIN favorecido f ON f.id = t.favorecido_id LEFT JOIN categoria cat ON cat.id = t.categoria_id
               WHERE t.estado = 'previsto' AND t.tipo IN ('despesa', 'receita') AND t.data_caixa <= %s
               ORDER BY t.data_caixa, t.criado_em""", (ate,)).fetchall():
        itens.append({"tipo": "previsto", **r})
    # transferências previstas: um evento por transferência (as duas pontas são confirmadas juntas); valor neutro
    vistas: dict = {}
    for r in cur.execute(
            """SELECT t.id, t.transferencia_id, t.valor_centavos, t.data_caixa AS data, t.descricao, c.nome AS conta_nome,
                      (SELECT c2.nome FROM transacao t2 JOIN conta c2 ON c2.id = t2.conta_id
                        WHERE t2.transferencia_id = t.transferencia_id AND t2.id <> t.id) AS contraparte_nome
               FROM transacao t JOIN conta c ON c.id = t.conta_id
               WHERE t.estado = 'previsto' AND t.tipo = 'transferencia' AND t.data_caixa <= %s
               ORDER BY t.data_caixa, t.valor_centavos""", (ate,)).fetchall():
        if r["transferencia_id"] not in vistas:       # a ponta de saída (valor negativo) vem primeiro
            vistas[r["transferencia_id"]] = r
    for r in vistas.values():
        saida = r["valor_centavos"] < 0
        itens.append({"tipo": "transferencia", "id": r["id"], "valor_centavos": abs(r["valor_centavos"]), "data": r["data"], "descricao": r["descricao"],
                      "origem_nome": r["conta_nome"] if saida else r["contraparte_nome"],
                      "destino_nome": r["contraparte_nome"] if saida else r["conta_nome"], "conta_nome": r["conta_nome"]})
    for r in cur.execute(
            """SELECT f.id, f.data_vencimento AS data, f.data_fechamento, k.id AS cartao_id, k.nome AS cartao_nome, k.conta_pagamento_id,
                      SUM(t.valor_centavos)::bigint AS valor_centavos
               FROM fatura f JOIN cartao k ON k.id = f.cartao_id JOIN transacao t ON t.fatura_id = f.id
               WHERE f.status <> 'paga' AND f.data_vencimento <= %s
               GROUP BY f.id, k.id HAVING SUM(t.valor_centavos) <> 0 ORDER BY f.data_vencimento""", (ate,)).fetchall():
        itens.append({"tipo": "fatura", "fechada": r["data_fechamento"] < hoje, **r})
    for i in itens:
        i["atrasado"] = i["data"] < hoje
    # a próxima fatura em aberto de cada cartão que vence depois do período também é mostrada (fora dos totais)
    for r in cur.execute(
            """SELECT DISTINCT ON (k.id) f.id, f.data_vencimento AS data, f.data_fechamento, k.id AS cartao_id, k.nome AS cartao_nome,
                      k.conta_pagamento_id, SUM(t.valor_centavos) OVER (PARTITION BY f.id)::bigint AS valor_centavos
               FROM fatura f JOIN cartao k ON k.id = f.cartao_id JOIN transacao t ON t.fatura_id = f.id
               WHERE f.status <> 'paga' AND f.data_vencimento > %s
               ORDER BY k.id, f.data_vencimento""", (ate,)).fetchall():
        if r["valor_centavos"]:
            itens.append({"tipo": "fatura", "fechada": r["data_fechamento"] < hoje, "atrasado": False, "alem_periodo": True, **r})
    itens.sort(key=lambda i: (i["data"], i["tipo"]))
    dentro = [i for i in itens if not i.get("alem_periodo") and i["tipo"] != "transferencia"]
    saidas = sum(i["valor_centavos"] for i in dentro if i["valor_centavos"] < 0)
    entradas = sum(i["valor_centavos"] for i in dentro if i["valor_centavos"] > 0)
    return {"hoje": hoje, "ate": ate, "itens": itens, "saidas": saidas, "entradas": entradas,
            "atrasados": sum(1 for i in itens if i["atrasado"] and not i.get("alem_periodo"))}
