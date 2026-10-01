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
