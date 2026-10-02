"""Recorrências com previstos até o horizonte (mês atual + 5) e propagação de edição/exclusão."""
from datetime import date

from conftest import conta


def mes_mais(n):
    a, m = date.today().year, date.today().month - 1 + n
    return f"{a + m // 12:04d}-{m % 12 + 1:02d}"


def nova(p):
    cc = conta(p, "Corrente", 0)
    r = p.post("/api/recorrencias", json={"tipo": "despesa", "valor_centavos": 10000, "dia_mes": 10, "conta_id": cc["id"],
                                          "favorecido_nome": "Internet SA", "descricao": "Internet", "inicio": f"{mes_mais(0)}-01"})
    assert r.status_code == 201, r.text
    ok = p.post("/api/recorrencias/gerar", json={"mes": mes_mais(0), "ate": mes_mais(5)})
    assert ok.status_code == 200 and ok.json()["criadas"] == 6
    return r.json(), cc


def ocorrencias(p, cc):
    return sorted((t for t in p.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 100, "ate": f"{mes_mais(8)}-28"}).json() if t["recorrencia_id"]),
                  key=lambda t: t["data_competencia"])


def test_gera_seis_meses_e_nao_duplica(nova_pessoa):
    p = nova_pessoa("hz")
    rec, cc = nova(p)
    assert len(ocorrencias(p, cc)) == 6
    assert p.post("/api/recorrencias/gerar", json={"mes": mes_mais(0), "ate": mes_mais(5)}).json()["criadas"] == 0     # idempotente


def test_editar_recorrencia_refaz_previstos_ate_o_horizonte_e_poupa_o_confirmado(nova_pessoa):
    p = nova_pessoa("hz2")
    rec, cc = nova(p)
    primeira = ocorrencias(p, cc)[0]
    assert p.post(f"/api/transacoes/{primeira['id']}/confirmar", json={"valor_centavos": 10500}).status_code == 200
    assert p.patch(f"/api/recorrencias/{rec['id']}", json={"valor_centavos": 12000, "a_partir_de": mes_mais(0)}).status_code == 200
    ts = ocorrencias(p, cc)
    assert len(ts) == 6
    assert (ts[0]["estado"], ts[0]["valor_centavos"]) == ("confirmado", -10500)
    assert all((t["estado"], t["valor_centavos"]) == ("previsto", -12000) for t in ts[1:])
    # pausar remove os previstos e reativar completa o horizonte de novo
    assert p.patch(f"/api/recorrencias/{rec['id']}", json={"ativa": False, "a_partir_de": mes_mais(0)}).json()["previstos_removidos"] == 5
    assert len(ocorrencias(p, cc)) == 1
    assert p.patch(f"/api/recorrencias/{rec['id']}", json={"ativa": True, "a_partir_de": mes_mais(0)}).status_code == 200
    assert len(ocorrencias(p, cc)) == 6


def test_excluir_recorrencia_remove_previstos_e_preserva_confirmados(nova_pessoa):
    p = nova_pessoa("hz3")
    rec, cc = nova(p)
    primeira = ocorrencias(p, cc)[0]
    p.post(f"/api/transacoes/{primeira['id']}/confirmar", json={})
    r = p.delete(f"/api/recorrencias/{rec['id']}")
    assert r.status_code == 200 and r.json()["previstos_removidos"] == 5
    resto = p.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 100, "ate": f"{mes_mais(8)}-28"}).json()
    assert [t["estado"] for t in resto] == ["confirmado"]


def test_excluir_recorrencia_mantendo_previstos(nova_pessoa):
    p = nova_pessoa("hz4")
    rec, cc = nova(p)
    r = p.delete(f"/api/recorrencias/{rec['id']}?previstos=manter")
    assert r.json()["previstos_removidos"] == 0
    assert len(p.get("/api/transacoes", params={"conta_id": cc["id"], "limite": 100, "ate": f"{mes_mais(8)}-28"}).json()) == 6


def test_excluir_ocorrencia_so_esta_ou_esta_e_as_proximas(nova_pessoa):
    p = nova_pessoa("hz5")
    rec, cc = nova(p)
    ts = ocorrencias(p, cc)
    assert p.delete(f"/api/transacoes/{ts[1]['id']}").status_code == 200                  # só este mês: pula
    assert len(ocorrencias(p, cc)) == 5
    r = p.delete(f"/api/transacoes/{ts[3]['id']}?proximos=true")                          # este e os próximos
    assert r.status_code == 200 and r.json()["proximos_removidos"] == 2
    restam = ocorrencias(p, cc)
    assert [t["data_competencia"][:7] for t in restam] == [mes_mais(0), mes_mais(2)]
    fim = next(x for x in p.get("/api/recorrencias").json() if x["id"] == rec["id"])["fim"]
    assert fim[:7] == mes_mais(2)                                                        # a recorrência termina no mês anterior
    assert p.post("/api/recorrencias/gerar", json={"mes": mes_mais(0), "ate": mes_mais(5)}).json()["criadas"] == 0


def test_editar_ocorrencia_e_propagar_para_os_proximos_meses(nova_pessoa):
    p = nova_pessoa("hz6")
    rec, cc = nova(p)
    ts = ocorrencias(p, cc)
    r = p.patch(f"/api/transacoes/{ts[2]['id']}", json={"valor_centavos": 13000, "propagar": True})
    assert r.status_code == 200, r.text
    novos = ocorrencias(p, cc)
    assert [t["valor_centavos"] for t in novos] == [-10000, -10000, -13000, -13000, -13000, -13000]
    assert next(x for x in p.get("/api/recorrencias").json() if x["id"] == rec["id"])["valor_centavos"] == 13000
    # sem propagar, só aquele mês muda
    r = p.patch(f"/api/transacoes/{novos[0]['id']}", json={"valor_centavos": 9000})
    assert [t["valor_centavos"] for t in ocorrencias(p, cc)] == [-9000, -10000, -13000, -13000, -13000, -13000]
