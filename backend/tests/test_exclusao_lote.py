"""Exclusão em lote (seleção de vários lançamentos)."""
from conftest import categoria_por_codigo, conta


def lanca(p, cc, valor, data, **kw):
    r = p.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": valor, "data_competencia": data, "conta_id": cc["id"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_excluir_varios_de_uma_vez(nova_pessoa):
    a = nova_pessoa("lote")
    cc = conta(a, "Corrente", 100000)
    ids = [lanca(a, cc, 1000 * (i + 1), "2026-09-10")[0]["id"] for i in range(4)]
    r = a.post("/api/transacoes/excluir-lote", json={"ids": ids[:3]})
    assert r.status_code == 200 and r.json() == {"excluidos": 3, "falhas": []}
    restantes = [t["id"] for t in a.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 50}).json()]
    assert restantes == [ids[3]]


def test_parcelamento_completo_e_falhas_nao_barram_o_resto(nova_pessoa):
    a, b = nova_pessoa("lote_a"), nova_pessoa("lote_b")
    cc, cb = conta(a, "Corrente", 100000), conta(b, "Do outro", 50000)
    parcelas = lanca(a, cc, 9000, "2026-09-10", parcelas=3)
    avulsa = lanca(a, cc, 500, "2026-09-11")[0]["id"]
    alheia = lanca(b, cb, 700, "2026-09-12")[0]["id"]
    r = a.post("/api/transacoes/excluir-lote", json={"ids": [parcelas[0]["id"], parcelas[1]["id"], avulsa, alheia], "todo_parcelamento": True}).json()
    assert r["excluidos"] == 4                                    # as 3 parcelas (uma só vez) + a avulsa
    assert [f["id"] for f in r["falhas"]] == [alheia]             # não enxerga o lançamento de outra pessoa
    assert a.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 50}).json() == []
    assert len(b.get("/api/transacoes", params={"conta_id": cb["id"], "limite": 50}).json()) == 1


def test_parcelamento_so_as_marcadas(nova_pessoa):
    a = nova_pessoa("lote_p")
    cc = conta(a, "Corrente", 100000)
    parcelas = lanca(a, cc, 9000, "2026-09-10", parcelas=3)
    assert a.post("/api/transacoes/excluir-lote", json={"ids": [parcelas[0]["id"]]}).json()["excluidos"] == 1
    assert len(a.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 50}).json()) == 2


def test_fatura_que_ficou_vazia_some(nova_pessoa):
    a = nova_pessoa("vazia")
    cc = conta(a, "Corrente", 100000)
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 28, "dia_vencimento": 4,
                                     "conta_pagamento_id": cc["id"], "limite_centavos": 800000, "final_principal": "1111"}).json()
    pl = k["plasticos"][0]["id"]
    t = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 3000, "data_competencia": "2026-09-10", "plastico_id": pl, "parcelas": 3}).json()
    assert len(a.get(f"/api/cartoes/{k['id']}/faturas").json()) == 3
    assert a.delete(f"/api/transacoes/{t[0]['id']}").status_code == 200           # exclui só a 1ª: as outras faturas continuam com a parcela
    assert len(a.get(f"/api/cartoes/{k['id']}/faturas").json()) == 2
    r = a.post("/api/transacoes/excluir-lote", json={"ids": [t[1]["id"]], "todo_parcelamento": True}).json()
    assert r["excluidos"] == 2 and a.get(f"/api/cartoes/{k['id']}/faturas").json() == []


def test_listagem_limpa_faturas_vazias_antigas(nova_pessoa):
    import psycopg
    from conftest import OWNER
    a = nova_pessoa("vazia2")
    cc = conta(a, "Corrente", 100000)
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 28, "dia_vencimento": 4,
                                     "conta_pagamento_id": cc["id"], "limite_centavos": 800000, "final_principal": "1111"}).json()
    a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 3000, "data_competencia": "2026-09-10", "plastico_id": k["plasticos"][0]["id"], "parcelas": 2})
    with psycopg.connect(OWNER, autocommit=True) as c:                               # simula a sobra de uma exclusão feita antes desta correção
        c.execute("DELETE FROM transacao WHERE plastico_id = %s", (k["plasticos"][0]["id"],))
    assert a.get(f"/api/cartoes/{k['id']}/faturas").json() == []
