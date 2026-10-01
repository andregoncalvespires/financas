"""Filtros e resumo da tela de lançamentos."""
from conftest import categoria_por_codigo, conta


def lanca(p, **kw):
    r = p.post("/api/transacoes", json={"tipo": "despesa", **kw})
    assert r.status_code == 201, r.text
    return r.json()[0]


def montar(p):
    cc = conta(p, "Corrente", 100000)
    cat = categoria_por_codigo(p, "2010.05")["id"]
    outra = next(c["id"] for c in p.get("/api/categorias").json() if c["id"] != cat and c["tipo"] == "despesa" and c["pai_id"] is None)
    k = p.post("/api/cartoes", json={"nome": "Visa", "dia_fechamento": 28, "dia_vencimento": 28, "conta_pagamento_id": cc["id"], "final_principal": "1111"}).json()
    pl = k["plasticos"][0]["id"]
    d = "2026-09-10"
    a = lanca(p, valor_centavos=1000, data_competencia=d, data_caixa=d, conta_id=cc["id"], categoria_id=cat, favorecido_nome="Padaria Sol", descricao="Pão")
    b = lanca(p, valor_centavos=2500, data_competencia=d, data_caixa=d, conta_id=cc["id"], categoria_id=outra, favorecido_nome="Mercado Lua", descricao="Compras_do_mês 50%")
    c = lanca(p, valor_centavos=4000, data_competencia=d, plastico_id=pl, categoria_id=cat, favorecido_nome="Padaria Sol", descricao="Lanche")
    r = p.post("/api/transacoes", json={"tipo": "receita", "valor_centavos": 9000, "data_competencia": d, "data_caixa": d, "conta_id": cc["id"]})
    assert r.status_code == 201
    return dict(cc=cc, k=k, pl=pl, cat=cat, outra=outra, a=a, b=b, c=c)


def ids(r):
    assert r.status_code == 200, r.text
    return {t["descricao"] for t in r.json()}


def test_filtros_combinados_e_cartao(nova_pessoa):
    p = nova_pessoa("fl")
    m = montar(p)
    fav = {f["nome"]: f["id"] for f in p.get("/api/favorecidos").json()}
    base = "/api/transacoes?de=2026-09-01&ate=2026-09-30"
    assert ids(p.get(base)) == {"Pão", "Compras_do_mês 50%", "Lanche", None}
    assert ids(p.get(f"{base}&favorecido_id={fav['Padaria Sol']}")) == {"Pão", "Lanche"}          # inclui a compra do cartão
    assert ids(p.get(f"{base}&categoria_id={m['outra']}")) == {"Compras_do_mês 50%"}
    assert ids(p.get(f"{base}&conta_id={m['cc']['id']}&tipo=despesa")) == {"Pão", "Compras_do_mês 50%"}   # cartão não é a conta
    assert ids(p.get(f"{base}&cartao_id={m['k']['id']}")) == {"Lanche"}
    assert ids(p.get(f"{base}&plastico_id={m['pl']}")) == {"Lanche"}
    assert ids(p.get(f"{base}&fatura_id={m['c']['fatura_id']}")) == {"Lanche"}
    assert ids(p.get(f"{base}&favorecido_id={fav['Padaria Sol']}&cartao_id={m['k']['id']}")) == {"Lanche"}
    assert ids(p.get("/api/transacoes?de=2026-10-01&ate=2026-10-31")) == set()                    # período


def test_busca_por_texto_e_caracteres_especiais(nova_pessoa):
    p = nova_pessoa("bs")
    montar(p)
    base = "/api/transacoes?de=2026-09-01&ate=2026-09-30"
    assert ids(p.get(f"{base}&busca=padaria")) == {"Pão", "Lanche"}           # favorecido, sem diferenciar maiúsculas
    assert ids(p.get(f"{base}&busca=lanche")) == {"Lanche"}                   # descrição
    assert ids(p.get(f"{base}&busca=50%25")) == {"Compras_do_mês 50%"}        # % é literal, não curinga
    assert ids(p.get(f"{base}&busca=s_d")) == {"Compras_do_mês 50%"}          # _ literal
    assert ids(p.get(f"{base}&busca=Compras%25do")) == set()                  # % não vira curinga
    assert ids(p.get(f"{base}&busca=Comprasxdo")) == set()                    # _ também não
    assert ids(p.get(f"{base}&busca=%25")) == {"Compras_do_mês 50%"}
    assert ids(p.get(f"{base}&busca=inexistente")) == set()


def test_resumo_filtrado_totais_e_quebras(nova_pessoa):
    p = nova_pessoa("rs")
    m = montar(p)
    base = "/api/transacoes/resumo?de=2026-09-01&ate=2026-09-30"
    r = p.get(base).json()
    assert r["receitas"] == 9000 and r["despesas"] == -(1000 + 2500 + 4000) and r["quantidade"] == 4
    nomes = {c["nome"]: c["total"] for c in r["por_categoria"]}
    assert nomes["Sem categoria"] == 9000 and sorted(nomes.values()) == [-5000, -2500, 9000]
    assert {f["nome"]: f["total"] for f in r["por_favorecido"]}["Padaria Sol"] == -5000
    k = p.get(f"{base}&cartao_id={m['k']['id']}").json()
    assert k["despesas"] == -4000 and k["receitas"] == 0 and k["quantidade"] == 1 and k["por_categoria"][0]["total"] == -4000
    assert p.get(f"{base}&busca=mercado").json()["despesas"] == -2500


def test_filtros_respeitam_privacidade(nova_pessoa):
    a, b = nova_pessoa("pa"), nova_pessoa("pb")
    m = montar(a)
    base = "/api/transacoes?de=2026-09-01&ate=2026-09-30"
    assert b.get(base).json() == [] and b.get(f"{base}&cartao_id={m['k']['id']}").json() == []
    assert b.get("/api/transacoes/resumo?de=2026-09-01&ate=2026-09-30").json()["quantidade"] == 0
