"""Contas de investimento: cadastro, rendimento previsto, premissas, valor informado, alerta e aviso por e-mail."""
from datetime import date, timedelta

from conftest import conta
from app.investimentos_calc import aliquota_ir, premissas_com_padrao, projetar, taxa_bruta_aa, taxa_poupanca_mensal
from app.routers import investimentos as inv_mod


def invest(p, nome="CDB Banco X", saldo=1000000):
    return conta(p, nome, saldo, tipo="investimento")


def cfg(p, c, **kw):
    corpo = {"subtipo": "cdb", "indexador": "cdi", "taxa": 100, "data_aplicacao": "2026-01-01", "dia_aniversario": 10, **kw}
    r = p.put(f"/api/contas/{c['id']}/investimento", json=corpo)
    assert r.status_code == 200, r.text
    return r


def rend(p, c):
    ts = p.get("/api/transacoes", params={"conta_id": c["id"], "limite": 100, "ate": "2030-12-31"}).json()
    return sorted(((t["data_competencia"], t["valor_centavos"], t["estado"]) for t in ts if t["origem"] == "rendimento"))


# ---------- cálculo puro ----------
def test_calculo_taxas_e_aliquotas():
    p = premissas_com_padrao(None)
    assert abs(taxa_bruta_aa("prefixado", 12.5, p) - 0.125) < 1e-9
    assert abs(taxa_bruta_aa("cdi", 100, p) - 0.139) < 1e-6
    assert taxa_bruta_aa("cdi", 110, p) > taxa_bruta_aa("cdi", 100, p)
    assert abs(taxa_bruta_aa("ipca", 6, p) - (1.045 * 1.06 - 1)) < 1e-9
    assert abs(taxa_poupanca_mensal(p) - 0.005) < 1e-9                                  # Selic > 8,5%: 0,5% a.m. + TR(0)
    assert abs(taxa_poupanca_mensal({**p, "selic": 8.0}) - ((1 + 0.7 * 0.08) ** (1 / 12) - 1)) < 1e-9
    assert [aliquota_ir(d) for d in (30, 180, 181, 360, 361, 720, 721)] == [0.225, 0.225, 0.20, 0.20, 0.175, 0.175, 0.15]


def test_projecao_para_no_vencimento_e_considera_aportes():
    p = premissas_com_padrao(None)
    inv = {"indexador": "prefixado", "taxa": 12.0, "dia_aniversario": 10, "data_vencimento": date(2026, 12, 20)}
    r = projetar(inv, p, 1000000, [], date(2026, 10, 2), 6)
    assert [d for d, _ in r] == [date(2026, 10, 10), date(2026, 11, 10), date(2026, 12, 10), date(2026, 12, 20)]   # o último período vai só até o vencimento
    com_aporte = projetar(inv, p, 1000000, [(date(2026, 10, 20), 500000)], date(2026, 10, 2), 3)
    assert com_aporte[0][1] == r[0][1] and com_aporte[1][1] > r[1][1]                # o aporte previsto aumenta a base dos meses seguintes
    assert projetar({**inv, "indexador": "manual"}, p, 1000000, [], date(2026, 10, 2), 6) == []


# ---------- cadastro e rendimento previsto ----------
def test_cadastro_gera_seis_rendimentos_previstos_e_recalcula(nova_pessoa):
    a = nova_pessoa("inv1")
    c = invest(a)
    cfg(a, c)
    r1 = rend(a, c)
    assert len(r1) == 6 and all(e == "previsto" and v > 0 for _, v, e in r1)
    assert a.post("/api/investimentos/recalcular").json() == {"criados": 0, "atualizados": 0, "removidos": 0}      # idempotente
    cfg(a, c, taxa=110)                                                           # mudar a taxa refaz os valores
    assert [v for _, v, _ in rend(a, c)] != [v for _, v, _ in r1] and len(rend(a, c)) == 6
    lista = a.get("/api/investimentos").json()
    item = next(i for i in lista["investimentos"] if i["id"] == c["id"])
    assert item["rotulo"] == "CDB" and item["aliquota_ir"] == aliquota_ir((date.today() - date(2026, 1, 1)).days)
    assert item["rendimento_proximo"] and item["rendimento_proximo_liquido"] < item["rendimento_proximo"]


def test_isento_nao_tem_ir_e_poupanca_usa_a_regra_propria(nova_pessoa):
    a = nova_pessoa("inv2")
    lci = invest(a, "LCI X")
    cfg(a, lci, subtipo="lci")
    poup = invest(a, "Poupança Y", 500000)
    cfg(a, poup, subtipo="poupanca", indexador=None, taxa=None)
    itens = {i["nome"]: i for i in a.get("/api/investimentos").json()["investimentos"]}
    assert itens["LCI X"]["aliquota_ir"] == 0 and itens["Poupança Y"]["aliquota_ir"] == 0
    assert abs(rend(a, poup)[0][1] - 500000 * 0.005) < 2                          # 0,5% a.m. sobre o saldo


def test_confirmar_com_valor_real_nao_e_sobrescrito(nova_pessoa):
    a = nova_pessoa("inv3")
    c = invest(a)
    cfg(a, c)
    ts = [t for t in a.get("/api/transacoes", params={"conta_id": c["id"], "limite": 100, "ate": "2030-12-31"}).json() if t["origem"] == "rendimento"]
    primeiro = sorted(ts, key=lambda t: t["data_competencia"])[0]
    assert a.post(f"/api/transacoes/{primeiro['id']}/confirmar", json={"valor_centavos": 9999}).status_code == 200
    a.post("/api/investimentos/recalcular")
    r = rend(a, c)
    assert r[0][1:] == (9999, "confirmado") and sum(1 for x in r if x[2] == "previsto") == 5     # confirmado fica; o mês não é projetado de novo


def test_premissas_alteram_o_rendimento(nova_pessoa):
    a = nova_pessoa("inv4")
    c = invest(a)
    cfg(a, c)
    antes = rend(a, c)[0][1]
    assert a.get("/api/premissas").json()["personalizadas"] is False
    r = a.put("/api/premissas", json={"selic": 10.0, "cdi": 9.9, "ipca": 4.0, "tr": 0})
    assert r.status_code == 200 and r.json()["personalizadas"] is True
    assert rend(a, c)[0][1] < antes                                              # menos CDI, menos rendimento (já recalculado ao salvar)


def test_regras_de_cadastro(nova_pessoa):
    a, b = nova_pessoa("inv5"), nova_pessoa("inv6")
    corrente = conta(a, "Corrente", 0)
    assert a.put(f"/api/contas/{corrente['id']}/investimento", json={"subtipo": "cdb", "indexador": "cdi", "taxa": 100, "dia_aniversario": 5}).status_code == 422
    c = invest(a)
    assert a.put(f"/api/contas/{c['id']}/investimento", json={"subtipo": "cdb", "indexador": "prefixado", "dia_aniversario": 5}).status_code == 422   # falta a taxa
    assert a.put(f"/api/contas/{c['id']}/investimento", json={"subtipo": "cdb", "indexador": "cdi", "taxa": 100}).status_code == 422                  # falta o aniversário
    assert a.put(f"/api/contas/{c['id']}/investimento", json={"subtipo": "cdb", "taxa": 100, "dia_aniversario": 5,
                                                              "data_aplicacao": "2026-05-01", "data_vencimento": "2026-04-01"}).status_code == 422
    assert b.put(f"/api/contas/{c['id']}/investimento", json={"subtipo": "cdb", "taxa": 100, "dia_aniversario": 5}).status_code in (403, 404)         # só o dono


def test_renda_variavel_valor_informado(nova_pessoa):
    a = nova_pessoa("inv7")
    c = invest(a, "Ações", 1000000)
    r = a.put(f"/api/contas/{c['id']}/investimento", json={"subtipo": "renda_variavel"})
    assert r.status_code == 200, r.text
    assert rend(a, c) == []                                                     # sem aniversário nem projeção
    assert a.post(f"/api/contas/{c['id']}/atualizar-valor", json={"valor_centavos": 1100000}).json()["diferenca_centavos"] == 100000
    assert next(x for x in a.get("/api/contas").json() if x["id"] == c["id"])["saldo_atual"] == 1100000
    assert a.post(f"/api/contas/{c['id']}/atualizar-valor", json={"valor_centavos": 1050000}).json()["diferenca_centavos"] == -50000
    assert next(x for x in a.get("/api/contas").json() if x["id"] == c["id"])["saldo_atual"] == 1050000


# ---------- alerta e e-mail ----------
def test_alerta_de_vencimento_nos_proximos_eventos_e_email_unico(nova_pessoa):
    a, outra = nova_pessoa("inv8"), nova_pessoa("inv9")
    c = invest(a, "CDB que vence")
    venc = date.today() + timedelta(days=10)
    cfg(a, c, data_vencimento=venc.isoformat(), alerta_dias=30)
    ev = [i for i in a.get("/api/lembretes?dias=7").json()["itens"] if i["tipo"] == "vencimento"]
    assert len(ev) == 1 and ev[0]["conta_nome"] == "CDB que vence" and ev[0]["data"] == venc.isoformat()
    assert all(i["tipo"] != "vencimento" for i in outra.get("/api/lembretes?dias=7").json()["itens"])       # só o dono vê o alerta
    assert a.get("/api/lembretes?dias=7").json()["saidas"] == 0                                              # não entra nos totais
    enviados = []
    n = inv_mod.avisar_vencimentos(enviar=lambda para, assunto, corpo: enviados.append((para, assunto)))
    assert n >= 1 and any(para == a.email and "CDB que vence" in assunto for para, assunto in enviados)
    again = []
    inv_mod.avisar_vencimentos(enviar=lambda para, assunto, corpo: again.append(para))
    assert a.email not in again                                                                              # um aviso por vencimento
    cfg(a, c, data_vencimento=(venc + timedelta(days=1)).isoformat())                                        # mudou o vencimento: avisa de novo
    novos = []
    inv_mod.avisar_vencimentos(enviar=lambda para, assunto, corpo: novos.append(para))
    assert a.email in novos


def test_vencimento_longe_nao_alerta(nova_pessoa):
    a = nova_pessoa("inv10")
    c = invest(a)
    cfg(a, c, data_vencimento=(date.today() + timedelta(days=200)).isoformat(), alerta_dias=30)
    assert all(i["tipo"] != "vencimento" for i in a.get("/api/lembretes?dias=7").json()["itens"])
    got = []
    inv_mod.avisar_vencimentos(enviar=lambda para, assunto, corpo: got.append(para))
    assert a.email not in got


def test_poupanca_nao_e_mais_tipo_padrao_mas_a_api_antiga_continua(nova_pessoa):
    a = nova_pessoa("inv11")
    nomes = {t["nome"] for t in a.get("/api/tipos-conta").json()}
    assert "Poupança" not in nomes and "Investimento" in nomes
    c = conta(a, "Reserva", 0, tipo="poupanca")                                   # chamada antiga: cai em Investimento
    assert c["tipo"] == "investimento"
    assert a.post("/api/tipos-conta", json={"nome": "Meu cofre", "classe": "poupanca"}).json()["classe"] == "investimento"


def test_ultimo_periodo_ate_o_vencimento_no_mesmo_mes_do_aniversario(nova_pessoa):
    a = nova_pessoa("inv12")
    c = invest(a)
    hoje = date.today()
    venc = hoje.replace(day=28) if hoje.day < 20 else hoje + timedelta(days=10)
    cfg(a, c, dia_aniversario=min(hoje.day + 0, 28), data_vencimento=venc.isoformat())
    datas = [d for d, _, _ in rend(a, c)]
    assert len(datas) == len(set(datas)) and max(datas) == venc.isoformat()          # o rendimento final cai exatamente no vencimento
    n = a.post("/api/investimentos/recalcular").json()
    assert n == {"criados": 0, "atualizados": 0, "removidos": 0}


def test_dois_rendimentos_no_mesmo_mes(nova_pessoa):
    a = nova_pessoa("inv13")
    c = invest(a)
    hoje = date.today()
    dia = 10
    # vencimento 2 dias depois do aniversário deste mês ou do próximo, para forçar dois lançamentos no mesmo mês
    base = hoje.replace(day=dia) if hoje.day <= dia else (hoje.replace(day=28) + timedelta(days=5)).replace(day=dia)
    cfg(a, c, dia_aniversario=dia, data_vencimento=(base + timedelta(days=2)).isoformat())
    meses = [d[:7] for d, _, _ in rend(a, c)]
    assert len(meses) >= 2 and meses[-1] == meses[-2]


# ---------- painel (evolução, cenários, alocação) e simulador ----------
def test_painel_cenarios_alocacao_e_permissao(nova_pessoa):
    a, b = nova_pessoa("pa"), nova_pessoa("pb")
    c1 = invest(a, "CDB", 1000000)
    cfg(a, c1)
    c2 = conta(a, "Ações", 500000, tipo="investimento")
    a.put(f"/api/contas/{c2['id']}/investimento", json={"subtipo": "renda_variavel"})
    r = a.get("/api/investimentos/painel", params={"meses": 12}).json()
    assert r["saldo_atual"] == 1500000
    assert [x["rotulo"] for x in r["alocacao"]] == ["CDB", "Renda variável (ações, FIIs, ETFs)"]
    assert abs(sum(x["percentual"] for x in r["alocacao"]) - 100) < 0.2
    assert set(r["cenarios"]) == {"pessimista", "base", "otimista"} and all(len(v) == 13 for v in r["cenarios"].values())
    fim = {k: v[-1][1] for k, v in r["cenarios"].items()}
    assert fim["pessimista"] < fim["base"] < fim["otimista"]
    assert fim["pessimista"] >= 1500000                                  # renda variável fica parada; CDB só rende
    assert r["final_base_liquido"] < r["final_base_bruto"] and r["ir_estimado_base"] > 0
    # outra pessoa não vê nada
    assert b.get("/api/investimentos/painel").json()["saldo_atual"] == 0


def test_painel_historico_usa_saldo_real(nova_pessoa):
    a = nova_pessoa("ph")
    c = invest(a, "CDB", 1000000)
    cfg(a, c)
    h = a.get("/api/investimentos/painel", params={"meses": 1, "historico": 3}).json()["passado"]
    assert len(h) <= 3 and all(v == 1000000 for _, v in h)


def test_simulador_aporte_e_validacoes(nova_pessoa):
    a = nova_pessoa("ps")
    c = invest(a, "CDB", 1000000)
    cfg(a, c)
    r = a.post("/api/investimentos/simular", json={"conta_id": c["id"], "meses": 12, "aporte_mensal_centavos": 50000}).json()
    assert r["aportado_liquido"] == 600000
    assert r["hipotese"]["final_bruto"] > r["base"]["final_bruto"] + 600000 - 1
    assert r["ganho_com_aportes"] > 0
    # sem conta: precisa da taxa
    assert a.post("/api/investimentos/simular", json={"meses": 12}).status_code == 422
    r = a.post("/api/investimentos/simular", json={"taxa_aa": 12, "saldo_inicial_centavos": 100000, "meses": 24}).json()
    assert r["hipotese"]["final_bruto"] > 100000
    # resgate depois do fim, conta manual e conta alheia
    assert a.post("/api/investimentos/simular", json={"conta_id": c["id"], "meses": 6, "resgate_centavos": 1, "mes_resgate": 7}).status_code == 422
    m = conta(a, "Ações", 100, tipo="investimento")
    a.put(f"/api/contas/{m['id']}/investimento", json={"subtipo": "renda_variavel"})
    assert a.post("/api/investimentos/simular", json={"conta_id": m["id"], "meses": 6}).status_code == 422
    assert a.post("/api/investimentos/simular", json={"conta_id": "00000000-0000-0000-0000-000000000000", "meses": 6}).status_code == 404
