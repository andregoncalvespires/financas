"""Editar, pausar e encerrar recorrências para os próximos meses."""
from conftest import categoria_por_codigo, conta


def previstos(p, rid_desc, de="2040-01-01", ate="2040-12-31"):
    ts = p.get(f"/api/transacoes?de={de}&ate={ate}&base=competencia&limite=500").json()
    return sorted(((t["data_competencia"], t["valor_centavos"], t["estado"], t["favorecido_nome"]) for t in ts if t["descricao"] == rid_desc))


def nova(p, **kw):
    cc = conta(p, "Corrente", 0)
    cat = categoria_por_codigo(p, "2010.05")["id"]
    r = p.post("/api/recorrencias", json={"tipo": "despesa", "valor_centavos": 10000, "dia_mes": 10, "conta_id": cc["id"], "categoria_id": cat,
                                          "favorecido_nome": "Luz SA", "descricao": "Conta de luz", "inicio": "2039-12-01", **kw})
    assert r.status_code == 201, r.text
    for m in ("2040-01", "2040-02", "2040-03"):
        assert p.post("/api/recorrencias/gerar", json={"mes": m}).status_code == 200
    return r.json(), cc


def test_editar_valor_dia_e_favorecido_refaz_previstos_sem_tocar_nos_confirmados(nova_pessoa):
    p = nova_pessoa("re")
    rec, cc = nova(p)
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10", "2040-02-10", "2040-03-10"]
    jan = next(t for t in p.get("/api/transacoes?de=2040-01-01&ate=2040-01-31").json() if t["descricao"] == "Conta de luz")
    assert p.post(f"/api/transacoes/{jan['id']}/confirmar", json={"valor_centavos": 11000}).status_code == 200
    r = p.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 15000, "dia_mes": 15, "favorecido_nome": "Energia Nova", "a_partir_de": "2040-01"})
    assert r.status_code == 200, r.text
    ps = previstos(p, "Conta de luz")
    assert ps[0] == ("2040-01-10", -11000, "confirmado", "Luz SA")                       # confirmado: intacto, e sem duplicar no mês
    assert ps[1:] == [("2040-02-15", -15000, "previsto", "Energia Nova"), ("2040-03-15", -15000, "previsto", "Energia Nova")]
    assert r.json()["valor_centavos"] == 15000 and r.json()["dia_mes"] == 15
    assert [x["valor_centavos"] for x in p.get("/api/recorrencias").json()] == [15000]


def test_a_partir_de_preserva_os_meses_anteriores(nova_pessoa):
    p = nova_pessoa("ap")
    rec, _ = nova(p)
    p.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 20000, "a_partir_de": "2040-03"})
    assert [(d, v) for d, v, *_ in previstos(p, "Conta de luz")] == [("2040-01-10", -10000), ("2040-02-10", -10000), ("2040-03-10", -20000)]


def test_pausar_remove_previstos_futuros_e_reativar_recria(nova_pessoa):
    p = nova_pessoa("pz")
    rec, _ = nova(p)
    r = p.patch(f"/api/recorrencias/{rec['id']}", json={"ativa": False, "a_partir_de": "2040-02"}).json()
    assert r["ativa"] is False and r["previstos_removidos"] == 2
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10"]
    assert p.post("/api/recorrencias/gerar", json={"mes": "2040-02"}).json()["criadas"] == 0       # pausada não gera
    r = p.patch(f"/api/recorrencias/{rec['id']}", json={"ativa": True, "a_partir_de": "2040-02"}).json()
    assert r["ativa"] is True and r["previstos_gerados"] >= 1
    assert "2040-02-10" in [x[0] for x in previstos(p, "Conta de luz")]


def test_definir_e_limpar_fim(nova_pessoa):
    p = nova_pessoa("fm")
    rec, _ = nova(p)
    p.patch(f"/api/recorrencias/{rec['id']}", json={"fim": "2040-02-28", "a_partir_de": "2040-01"})
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10", "2040-02-10"]
    r = p.patch(f"/api/recorrencias/{rec['id']}", json={"limpar_fim": True, "a_partir_de": "2040-01"}).json()
    assert r["fim"] is None
    assert p.post("/api/recorrencias/gerar", json={"mes": "2040-03"}).json()["criadas"] in (0, 1)
    assert "2040-03-10" in [x[0] for x in previstos(p, "Conta de luz")]


def test_editar_recorrencia_de_outra_pessoa_e_recusado(nova_pessoa):
    a, b = nova_pessoa("oa"), nova_pessoa("ob")
    rec, _ = nova(a)
    assert b.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 1}).status_code == 404
    assert a.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 0}).status_code == 422
    assert a.get("/api/recorrencias").json()[0]["valor_centavos"] == 10000


def test_excluir_ocorrencia_pula_o_mes_e_nao_volta(nova_pessoa):
    p = nova_pessoa("pl")
    rec, _ = nova(p)
    fev = next(t for t in p.get("/api/transacoes?de=2040-02-01&ate=2040-02-28").json() if t["descricao"] == "Conta de luz")
    assert fev["recorrencia_id"] == rec["id"]
    assert p.delete(f"/api/transacoes/{fev['id']}").status_code == 200
    assert p.get(f"/api/recorrencias/{rec['id']}/pulados").json() == ["2040-02-01"]
    assert p.post("/api/recorrencias/gerar", json={"mes": "2040-02"}).json()["criadas"] == 0          # não é recriado
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10", "2040-03-10"]               # os outros meses seguem
    # editar a recorrência refaz os previstos, mas respeita o mês pulado
    p.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 12000, "a_partir_de": "2040-01"})
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10", "2040-03-10"]
    # desfazer: o mês volta a ser gerado
    r = p.delete(f"/api/recorrencias/{rec['id']}/pulados/2040-02")
    assert r.status_code == 200 and r.json()["previstos_gerados"] == 1
    assert [x[0] for x in previstos(p, "Conta de luz")] == ["2040-01-10", "2040-02-10", "2040-03-10"]
    assert p.get(f"/api/recorrencias/{rec['id']}/pulados").json() == []
    assert p.delete(f"/api/recorrencias/{rec['id']}/pulados/2040-02").status_code == 404
    assert p.delete(f"/api/recorrencias/{rec['id']}/pulados/fev").status_code == 422


def test_excluir_ocorrencia_ja_confirmada_tambem_pula(nova_pessoa):
    p = nova_pessoa("pc")
    rec, _ = nova(p)
    jan = next(t for t in p.get("/api/transacoes?de=2040-01-01&ate=2040-01-31").json() if t["descricao"] == "Conta de luz")
    p.post(f"/api/transacoes/{jan['id']}/confirmar")
    assert p.delete(f"/api/transacoes/{jan['id']}").status_code == 200
    assert p.post("/api/recorrencias/gerar", json={"mes": "2040-01"}).json()["criadas"] == 0


def test_meses_pulados_respeitam_privacidade(nova_pessoa):
    a, b = nova_pessoa("qa"), nova_pessoa("qb")
    rec, _ = nova(a)
    t = next(t for t in a.get("/api/transacoes?de=2040-01-01&ate=2040-01-31").json() if t["descricao"] == "Conta de luz")
    a.delete(f"/api/transacoes/{t['id']}")
    assert b.get(f"/api/recorrencias/{rec['id']}/pulados").json() == []
    assert b.delete(f"/api/recorrencias/{rec['id']}/pulados/2040-01").status_code == 404
    assert a.get(f"/api/recorrencias/{rec['id']}/pulados").json() == ["2040-01-01"]
