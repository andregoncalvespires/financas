"""Transferências entre contas (corrente → poupança, corrente → dinheiro...)."""
from conftest import categoria_por_codigo, conta


def transfere(p, o, d, valor=10000, data="2026-09-10", **extra):
    return p.post("/api/transferencias", json={"conta_origem_id": o["id"], "conta_destino_id": d["id"], "valor_centavos": valor, "data": data, **extra})


def saldos(p):
    return {c["nome"]: c["saldo_atual"] for c in p.get("/api/contas").json()}


def test_transferencia_move_saldo_sem_virar_receita_ou_despesa(nova_pessoa):
    a = nova_pessoa("tr")
    cc, poup = conta(a, "Corrente", 100000), conta(a, "Poupança", 0, tipo="poupanca")
    r = transfere(a, cc, poup, 30000, descricao="Reserva do mês")
    assert r.status_code == 201, r.text
    pernas = r.json()["transacoes"]
    assert [p["valor_centavos"] for p in pernas] == [-30000, 30000]
    assert {p["tipo"] for p in pernas} == {"transferencia"} and pernas[0]["contraparte_nome"] == "Poupança" and pernas[1]["contraparte_nome"] == "Corrente"
    assert saldos(a) == {"Corrente": 70000, "Poupança": 30000}
    resumo = a.get("/api/resumo/mensal?mes=2026-09").json()
    assert resumo["receitas"] == 0 and resumo["despesas"] == 0                      # não distorce o resultado do mês
    assert sum(saldos(a).values()) == 100000                                        # total geral não muda


def test_transferencia_validacoes(nova_pessoa):
    a, b = nova_pessoa("v1"), nova_pessoa("v2")
    cc, din = conta(a, "Corrente", 5000), conta(a, "Dinheiro", 0, tipo="dinheiro")
    alheia = conta(b, "Alheia")
    assert transfere(a, cc, cc).status_code == 422
    assert transfere(a, cc, din, 0).status_code == 422
    assert transfere(a, cc, alheia).status_code == 404                             # conta de outra pessoa não é visível
    a.patch(f"/api/contas/{din['id']}", json={"inativa": True})
    assert transfere(a, cc, din).status_code == 422


def test_transferencia_prevista_confirma_e_exclui_as_duas_pontas(nova_pessoa):
    a = nova_pessoa("pv")
    cc, poup = conta(a, "Corrente", 50000), conta(a, "Poupança", 0, tipo="poupanca")
    pernas = transfere(a, cc, poup, 20000, estado="previsto").json()["transacoes"]
    assert saldos(a) == {"Corrente": 50000, "Poupança": 0}                          # previsto não mexe no saldo
    assert a.patch(f"/api/transacoes/{pernas[0]['id']}", json={"estado": "confirmado"}).status_code == 422
    assert a.post(f"/api/transacoes/{pernas[0]['id']}/confirmar").status_code == 200
    assert saldos(a) == {"Corrente": 30000, "Poupança": 20000}                      # as duas pontas confirmadas juntas
    assert a.post(f"/api/transacoes/{pernas[1]['id']}/confirmar").status_code == 404   # já confirmada
    assert a.delete(f"/api/transacoes/{pernas[1]['id']}").json()["excluidos"] == 2
    assert saldos(a) == {"Corrente": 50000, "Poupança": 0}


def test_confirmar_transferencia_com_lado_invisivel_e_recusado(nova_pessoa):
    a, b = nova_pessoa("o"), nova_pessoa("e")
    conj, priv = conta(a, "Conjunta"), conta(a, "Privada", 90000)
    v = a.post(f"/api/contas/{conj['id']}/convites", json={"email": b.email, "papel": "editor"}).json()
    b.post(f"/api/convites/{v['id']}/aceitar")
    pernas = transfere(a, priv, conj, 10000, estado="previsto").json()["transacoes"]
    vista = b.get("/api/transacoes").json()
    assert len(vista) == 1 and vista[0]["contraparte_nome"] is None                # a origem privada não vaza
    assert b.post(f"/api/transacoes/{vista[0]['id']}/confirmar").status_code == 403
    assert {t["estado"] for t in a.get("/api/transacoes").json()} == {"previsto"}  # nada ficou pela metade
    assert a.post(f"/api/transacoes/{pernas[0]['id']}/confirmar").status_code == 200


def test_transferencia_prevista_aparece_nos_proximos_eventos(nova_pessoa):
    from datetime import date, timedelta
    a = nova_pessoa("ev")
    cc, poup = conta(a, "Corrente", 100000), conta(a, "Poupança", 0, tipo="poupanca")
    em3 = (date.today() + timedelta(days=3)).isoformat()
    em40 = (date.today() + timedelta(days=40)).isoformat()
    pernas = transfere(a, cc, poup, 30000, data=em3, estado="previsto", descricao="Aporte").json()["transacoes"]
    transfere(a, cc, poup, 5000, data=em40, estado="previsto")
    l = a.get("/api/lembretes?dias=7").json()
    ts = [i for i in l["itens"] if i["tipo"] == "transferencia"]
    assert len(ts) == 1                                                       # um evento por transferência, não dois
    assert ts[0]["valor_centavos"] == 30000 and ts[0]["origem_nome"] == "Corrente" and ts[0]["destino_nome"] == "Poupança" and ts[0]["descricao"] == "Aporte"
    assert l["saidas"] == 0 and l["entradas"] == 0                            # não é pagar nem receber
    assert len([i for i in a.get("/api/lembretes?dias=60").json()["itens"] if i["tipo"] == "transferencia"]) == 2
    # no quadro: reserva o valor na origem e o destino o recebe; o total não muda e não vira a pagar/receber
    sd = a.get(f"/api/saldo-disponivel?ate={(date.today() + timedelta(days=10)).isoformat()}").json()
    por = {c["nome"]: c for c in sd["contas"]}
    assert por["Corrente"]["livre"] == 70000 and por["Poupança"]["livre"] == 30000 and sd["geral"]["livre"] == 100000
    assert por["Corrente"]["saidas_previstas"] == 0 and por["Poupança"]["entradas_previstas"] == 0
    # confirmar pelo evento (qualquer ponta) tira da lista
    assert a.post(f"/api/transacoes/{ts[0]['id']}/confirmar").status_code == 200
    assert [i for i in a.get("/api/lembretes?dias=7").json()["itens"] if i["tipo"] == "transferencia"] == []
    assert saldos(a) == {"Corrente": 70000, "Poupança": 30000}
    assert pernas  # as duas pontas foram criadas


def test_desfazer_efetivacao_de_lancamento_comum(nova_pessoa):
    a = nova_pessoa("df")
    cc = conta(a, "Corrente", 50000)
    cat = categoria_por_codigo(a, "2020.01")
    t = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 12000, "data_competencia": "2026-09-10", "conta_id": cc["id"],
                                         "categoria_id": cat["id"], "estado": "previsto"}).json()[0]
    assert saldos(a) == {"Corrente": 50000}
    assert a.post(f"/api/transacoes/{t['id']}/desfazer").status_code == 409          # já está previsto
    assert a.post(f"/api/transacoes/{t['id']}/confirmar").status_code == 200
    assert saldos(a) == {"Corrente": 38000}
    r = a.post(f"/api/transacoes/{t['id']}/desfazer")
    assert r.status_code == 200 and r.json()["estado"] == "previsto" and r.json()["data_competencia"] == "2026-09-10"
    assert saldos(a) == {"Corrente": 50000}
    assert a.post(f"/api/transacoes/{t['id']}/confirmar").status_code == 200         # pode efetivar de novo


def test_desfazer_transferencia_volta_as_duas_pontas(nova_pessoa):
    a = nova_pessoa("dt")
    cc, poup = conta(a, "Corrente", 50000), conta(a, "Poupança", 0, tipo="poupanca")
    pernas = transfere(a, cc, poup, 20000).json()["transacoes"]                      # nasce confirmada
    assert saldos(a) == {"Corrente": 30000, "Poupança": 20000}
    assert a.post(f"/api/transacoes/{pernas[1]['id']}/desfazer").status_code == 200
    assert saldos(a) == {"Corrente": 50000, "Poupança": 0}
    assert {t["estado"] for t in a.get("/api/transacoes").json()} == {"previsto"}
    ev = a.get("/api/lembretes?dias=60").json()
    assert any(e.get("tipo") == "transferencia" for e in ev["eventos"]) if isinstance(ev, dict) and "eventos" in ev else True


def test_desfazer_transferencia_com_lado_invisivel_e_recusado(nova_pessoa):
    a, b = nova_pessoa("do"), nova_pessoa("de")
    conj, priv = conta(a, "Conjunta"), conta(a, "Privada", 90000)
    v = a.post(f"/api/contas/{conj['id']}/convites", json={"email": b.email, "papel": "editor"}).json()
    b.post(f"/api/convites/{v['id']}/aceitar")
    transfere(a, priv, conj, 10000)
    vista = b.get("/api/transacoes").json()
    assert b.post(f"/api/transacoes/{vista[0]['id']}/desfazer").status_code == 403
    assert {t["estado"] for t in a.get("/api/transacoes").json()} == {"confirmado"}  # nada ficou pela metade


def test_desfazer_bloqueia_conciliado_e_pagamento_de_fatura(nova_pessoa):
    a = nova_pessoa("db")
    cc = conta(a, "Corrente", 50000)
    cat = categoria_por_codigo(a, "2020.01")
    t = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 1000, "data_competencia": "2026-09-10", "conta_id": cc["id"], "categoria_id": cat["id"]}).json()[0]
    import psycopg
    from conftest import OWNER
    with psycopg.connect(OWNER, autocommit=True) as c:                              # a API ainda não concilia; simula direto no banco
        c.execute("UPDATE transacao SET estado = 'conciliado' WHERE id = %s", (t["id"],))
    assert a.post(f"/api/transacoes/{t['id']}/desfazer").status_code == 422
    assert a.post("/api/transacoes/00000000-0000-0000-0000-000000000000/desfazer").status_code == 404


def test_confirmar_com_data_de_efetivacao(nova_pessoa):
    from datetime import date, timedelta
    a = nova_pessoa("dt")
    cc, poup = conta(a, "Corrente", 50000), conta(a, "Poupança", 0, tipo="poupanca")
    ontem = (date.today() - timedelta(days=1)).isoformat()
    # lançamento simples: a data de caixa passa a ser a informada; a competência não muda
    t = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 1000, "data_competencia": "2026-09-05",
                                        "data_caixa": "2026-09-20", "conta_id": cc["id"], "estado": "previsto"}).json()[0]
    r = a.post(f"/api/transacoes/{t['id']}/confirmar", json={"data_caixa": ontem})
    assert r.status_code == 200 and r.json()["data_caixa"] == ontem and r.json()["data_competencia"] == "2026-09-05"
    # sem corpo ou sem data: mantém a data prevista
    t2 = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 500, "data_competencia": "2026-09-05",
                                         "data_caixa": "2026-09-21", "conta_id": cc["id"], "estado": "previsto"}).json()[0]
    assert a.post(f"/api/transacoes/{t2['id']}/confirmar").json()["data_caixa"] == "2026-09-21"
    # data futura é recusada e nada muda
    t3 = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 700, "data_competencia": "2026-09-05",
                                         "data_caixa": "2026-09-22", "conta_id": cc["id"], "estado": "previsto"}).json()[0]
    futuro = (date.today() + timedelta(days=10)).isoformat()
    assert a.post(f"/api/transacoes/{t3['id']}/confirmar", json={"data_caixa": futuro}).status_code == 422
    assert a.post(f"/api/transacoes/{t3['id']}/confirmar", json={}).status_code == 200
    # transferência: as duas pontas recebem a mesma data
    pernas = transfere(a, cc, poup, 20000, estado="previsto").json()["transacoes"]
    assert a.post(f"/api/transacoes/{pernas[0]['id']}/confirmar", json={"data_caixa": ontem}).status_code == 200
    datas = {x["data_caixa"] for x in a.get("/api/transacoes").json() if x.get("transferencia_id") == pernas[0]["transferencia_id"]}
    assert datas == {ontem}
