from datetime import date, timedelta

from conftest import categoria_por_codigo, conta

HOJE = date.today()


def lanca(p, **kw):
    r = p.post("/api/transacoes", json={"tipo": "despesa", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_saldo_disponivel_calculado_a_partir_dos_previstos(nova_pessoa):
    a = nova_pessoa()
    cc = conta(a, "Corrente", 100000)
    cat = categoria_por_codigo(a, "2010.05")["id"]
    d = lambda n: (HOJE + timedelta(days=n)).isoformat()
    boleto = lanca(a, valor_centavos=20000, data_competencia=d(0), data_caixa=d(10), conta_id=cc["id"], categoria_id=cat, forma_pagamento="boleto", estado="previsto")[0]
    lanca(a, valor_centavos=5000, data_competencia=d(0), data_caixa=d(5), conta_id=cc["id"], categoria_id=cat, forma_pagamento="debito_automatico", estado="previsto")
    lanca(a, valor_centavos=99999, data_competencia=d(0), data_caixa=d(100), conta_id=cc["id"], categoria_id=cat, estado="previsto")    # fora da janela
    a.post("/api/transacoes", json={"tipo": "receita", "valor_centavos": 300000, "data_competencia": d(0), "data_caixa": d(20), "conta_id": cc["id"], "estado": "previsto"})
    k = a.post("/api/cartoes", json={"nome": "Visa", "dia_fechamento": 28, "dia_vencimento": 28, "conta_pagamento_id": cc["id"], "final_principal": "1111"}).json()
    compra = lanca(a, valor_centavos=30000, data_competencia=HOJE.replace(day=1).isoformat(), plastico_id=k["plasticos"][0]["id"], categoria_id=cat)[0]
    # o vencimento da fatura depende do dia do mês em que o teste roda: a janela vai até o que for maior, 30 dias ou esse vencimento
    ate = max(d(30), compra["data_caixa"])

    s = a.get(f"/api/saldo-disponivel?ate={ate}").json()
    c = s["contas"][0]
    assert c["saldo_atual"] == 100000
    assert c["por_forma"] == {"boleto": -20000, "debito_automatico": -5000}
    assert c["saidas_previstas"] == -25000 and c["entradas_previstas"] == 300000
    assert c["faturas_total"] == -30000 and len(c["faturas"]) == 1
    assert c["livre"] == 100000 - 25000 - 30000 and c["projetado"] == c["livre"] + 300000
    assert s["geral"]["livre"] == c["livre"]

    # confirmar o boleto move o valor de "previsto" para o saldo atual
    assert a.post(f"/api/transacoes/{boleto['id']}/confirmar").status_code == 200
    c2 = a.get(f"/api/saldo-disponivel?ate={ate}").json()["contas"][0]
    assert c2["saldo_atual"] == 80000 and c2["livre"] == c["livre"]           # o livre não muda: já estava reservado


def test_recorrencia_gera_previstos_sem_duplicar(nova_pessoa):
    a = nova_pessoa()
    cc = conta(a, "Corrente", 0)
    cat = categoria_por_codigo(a, "2010.06")["id"]
    r = a.post("/api/recorrencias", json={"tipo": "despesa", "valor_centavos": 3990, "dia_mes": 31, "conta_id": cc["id"], "categoria_id": cat,
                                          "favorecido_nome": "Streaming", "forma_pagamento": "debito_automatico", "inicio": "2026-01-01"})
    assert r.status_code == 201, r.text
    assert a.post("/api/recorrencias/gerar", json={"mes": "2026-02"}).json() == {"criadas": 1}
    assert a.post("/api/recorrencias/gerar", json={"mes": "2026-02"}).json() == {"criadas": 0}
    ts = a.get("/api/transacoes?de=2026-02-01&ate=2026-02-28").json()
    assert len(ts) == 1 and ts[0]["data_competencia"] == "2026-02-28" and ts[0]["estado"] == "previsto" and ts[0]["origem"] == "recorrencia"
    assert a.post("/api/recorrencias/gerar", json={"mes": "2026-03"}).json() == {"criadas": 1}


def test_resumo_mensal_por_grupo(nova_pessoa):
    a = nova_pessoa()
    cc = conta(a, "Corrente", 0)
    for cod, v in (("2020.01", 10000), ("2020.02", 2500), ("2060.03", 8000)):
        lanca(a, valor_centavos=v, data_competencia="2026-05-10", conta_id=cc["id"], categoria_id=categoria_por_codigo(a, cod)["id"])
    a.post("/api/transacoes", json={"tipo": "receita", "valor_centavos": 500000, "data_competencia": "2026-05-05", "conta_id": cc["id"],
                                    "categoria_id": categoria_por_codigo(a, "1000.01")["id"]})
    r = a.get("/api/resumo/mensal?mes=2026-05").json()
    assert r["receitas"] == 500000 and r["despesas"] == -20500 and r["resultado"] == 479500
    assert [g["grupo"] for g in r["grupos"]] == ["Lazer", "Alimentação"] or [g["grupo"] for g in r["grupos"]] == ["Alimentação", "Lazer"]
    alim = next(g for g in r["grupos"] if g["grupo"] == "Alimentação")
    assert alim["total"] == -12500 and len(alim["categorias"]) == 2


def test_projetado_e_saldo_mais_entradas_saidas_e_faturas(nova_pessoa):
    """O que a tela de Início mostra como Disponível/Total (projetado) tem que fechar com as parcelas exibidas: saldo + a receber + a pagar + faturas."""
    from datetime import date, timedelta
    from conftest import conta
    a = nova_pessoa("fecha")
    c = conta(a, "Corrente", 100000)
    hoje = date.today()
    for tipo, v in (("despesa", 20000), ("despesa", 5000), ("receita", 300000)):
        r = a.post("/api/transacoes", json={"tipo": tipo, "valor_centavos": v, "data_competencia": hoje.isoformat(), "data_caixa": hoje.isoformat(),
                                           "conta_id": c["id"], "estado": "previsto"})
        assert r.status_code == 201, r.text
    s = a.get(f"/api/saldo-disponivel?ate={hoje + timedelta(days=60)}").json()
    g = s["geral"]
    assert g["projetado"] == g["saldo_atual"] + g["entradas_previstas"] + g["saidas_previstas"] + g["faturas"]
    assert g["projetado"] == 100000 + 300000 - 25000
    assert g["livre"] == 100000 - 25000                        # `livre` segue sendo o valor sem as entradas
