"""Cenário central: cartão principal do dono com plástico adicional usado por outro usuário (portador)."""
import pytest

from conftest import categoria_por_codigo, conta


@pytest.fixture()
def cenario(nova_pessoa):
    a, b = nova_pessoa("dono"), nova_pessoa("portador")
    cc = conta(a, "Corrente", 500000)
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 10, "dia_vencimento": 20,
                                     "conta_pagamento_id": cc["id"], "limite_centavos": 800000, "final_principal": "1234"})
    assert k.status_code == 201, k.text
    k = k.json()
    pl = a.post(f"/api/cartoes/{k['id']}/plasticos", json={"final": "5678", "rotulo": "Maria"})
    assert pl.status_code == 201, pl.text
    adicional = pl.json()
    principal = next(p for p in k["plasticos"] if p["final"] == "1234")
    v = a.post(f"/api/plasticos/{adicional['id']}/convites", json={"email": b.email}).json()
    assert b.post(f"/api/convites/{v['id']}/aceitar").status_code == 200
    return dict(a=a, b=b, conta=cc, cartao=k, principal=principal, adicional=adicional,
                cat_a=categoria_por_codigo(a, "2020.01"))


def compra(p, plastico_id, cat, valor, data, **extra):
    return p.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": valor, "data_competencia": data,
                                          "plastico_id": plastico_id, "categoria_id": cat, **extra})


def test_portador_lanca_no_plastico_dele_e_cai_na_fatura_do_dono(cenario):
    a, b, s = cenario["a"], cenario["b"], cenario
    cat = categoria_por_codigo(b, "2020.01", dono_id=a.id)          # o portador usa o cadastro do dono
    r = compra(b, s["adicional"]["id"], cat["id"], 4500, "2026-09-05", favorecido_nome="Padaria")
    assert r.status_code == 201, r.text
    t = r.json()[0]
    assert t["valor_centavos"] == -4500 and t["data_caixa"] == "2026-09-20" and t["criado_por"] == b.id
    # compra no dia do fechamento ainda entra na fatura que fecha; no dia seguinte vai para a próxima
    assert compra(b, s["adicional"]["id"], cat["id"], 1000, "2026-09-10").json()[0]["data_caixa"] == "2026-09-20"
    assert compra(b, s["adicional"]["id"], cat["id"], 2000, "2026-09-11").json()[0]["data_caixa"] == "2026-10-20"
    # o dono lança no plástico principal
    assert compra(a, s["principal"]["id"], s["cat_a"]["id"], 30000, "2026-09-06").status_code == 201

    faturas = a.get(f"/api/cartoes/{s['cartao']['id']}/faturas").json()
    set_ = next(f for f in faturas if f["data_vencimento"] == "2026-09-20")
    assert set_["total"] == -(4500 + 1000 + 30000) and {q["final"] for q in set_["por_plastico"]} == {"1234", "5678"}
    assert len(a.get(f"/api/transacoes?fatura_id={set_['id']}").json()) == 3


def test_portador_enxerga_apenas_o_que_e_dele(cenario):
    a, b, s = cenario["a"], cenario["b"], cenario
    cat_b = categoria_por_codigo(b, "2020.01", dono_id=a.id)
    compra(b, s["adicional"]["id"], cat_b["id"], 4500, "2026-09-05")
    compra(a, s["principal"]["id"], s["cat_a"]["id"], 30000, "2026-09-06")

    vistas = b.get("/api/transacoes").json()
    assert [t["valor_centavos"] for t in vistas] == [-4500]                       # a compra do dono é invisível
    cartoes = b.get("/api/cartoes").json()
    assert len(cartoes) == 1 and [p["final"] for p in cartoes[0]["plasticos"]] == ["5678"]
    assert cartoes[0]["conta_pagamento_id"] is None and cartoes[0]["limite_centavos"] is None
    assert b.get(f"/api/cartoes/{s['cartao']['id']}/faturas").status_code == 404   # sem acesso à fatura
    assert b.get("/api/contas").json() == []                                        # nem à conta que paga
    assert compra(b, s["principal"]["id"], cat_b["id"], 100, "2026-09-07").status_code == 404   # o plástico do dono nem existe para ele
    # categoria do próprio portador não vale: cadastros são os do dono
    cat_propria = categoria_por_codigo(b, "2020.01", dono_id=b.id)
    assert compra(b, s["adicional"]["id"], cat_propria["id"], 100, "2026-09-07").status_code == 422

    gastos = b.get("/api/portador/meus-gastos").json()
    assert len(gastos) == 1 and gastos[0]["final"] == "5678" and gastos[0]["faturas"][0]["total"] == -4500
    assert "total_fatura" not in str(gastos)


def test_pagar_fatura_baixa_a_conta_e_trava_o_portador(cenario):
    a, b, s = cenario["a"], cenario["b"], cenario
    cat_b = categoria_por_codigo(b, "2020.01", dono_id=a.id)
    tb = compra(b, s["adicional"]["id"], cat_b["id"], 4500, "2026-09-05").json()[0]
    compra(a, s["principal"]["id"], s["cat_a"]["id"], 30000, "2026-09-06")
    fat = next(f for f in a.get(f"/api/cartoes/{s['cartao']['id']}/faturas").json() if f["data_vencimento"] == "2026-09-20")

    r = a.post(f"/api/faturas/{fat['id']}/pagar", json={"conta_id": s["conta"]["id"], "data": "2026-09-20"})
    assert r.status_code == 200 and r.json()["valor_centavos"] == 34500
    assert a.get("/api/contas").json()[0]["saldo_atual"] == 500000 - 34500          # a despesa só pesa no caixa quando a fatura é paga
    assert a.post(f"/api/faturas/{fat['id']}/pagar", json={"conta_id": s["conta"]["id"]}).status_code == 409
    assert b.patch(f"/api/transacoes/{tb['id']}", json={"valor_centavos": 1}).status_code in (403, 404)   # fatura paga: travada
    # lançamento tardio com data dentro da fatura paga vai para a próxima
    tardio = compra(b, s["adicional"]["id"], cat_b["id"], 900, "2026-09-08").json()[0]
    assert tardio["data_caixa"] == "2026-10-20"
    # desfazer o pagamento reabre a fatura
    pag = next(t for t in a.get("/api/transacoes?tipo=pagamento_fatura").json())
    assert a.delete(f"/api/transacoes/{pag['id']}").status_code == 200
    assert next(f for f in a.get(f"/api/cartoes/{s['cartao']['id']}/faturas").json() if f["id"] == fat["id"])["status"] == "aberta"
    assert a.get("/api/contas").json()[0]["saldo_atual"] == 500000


def test_parcelamento_distribui_em_faturas_seguintes(cenario):
    a, s = cenario["a"], cenario
    r = compra(a, s["principal"]["id"], s["cat_a"]["id"], 30001, "2026-09-05", parcelas=3)
    ts = r.json()
    assert [t["valor_centavos"] for t in ts] == [-10001, -10000, -10000]
    assert [t["data_caixa"] for t in ts] == ["2026-09-20", "2026-10-20", "2026-11-20"]
    assert [t["estado"] for t in ts] == ["confirmado", "previsto", "previsto"]
    assert [f"{t['numero_parcela']}/{t['total_parcelas']}" for t in ts] == ["1/3", "2/3", "3/3"]
    assert a.delete(f"/api/transacoes/{ts[0]['id']}?todo_parcelamento=true").json()["excluidos"] == 3


def test_fechamento_maior_que_vencimento_atravessa_o_ano(nova_pessoa):
    a = nova_pessoa()
    k = a.post("/api/cartoes", json={"nome": "Master", "dia_fechamento": 25, "dia_vencimento": 5, "final_principal": "9999"}).json()
    pl = k["plasticos"][0]["id"]
    cat = categoria_por_codigo(a, "2020.01")["id"]
    assert compra(a, pl, cat, 100, "2026-12-20").json()[0]["data_caixa"] == "2027-01-05"
    assert compra(a, pl, cat, 100, "2026-12-28").json()[0]["data_caixa"] == "2027-02-05"


def test_dono_remove_portador_e_acesso_some(cenario):
    a, b, s = cenario["a"], cenario["b"], cenario
    assert a.delete(f"/api/plasticos/{s['adicional']['id']}/portador").status_code == 200
    assert b.get("/api/cartoes").json() == []
    cat_b = categoria_por_codigo(b, "2020.01", dono_id=b.id)
    assert compra(b, s["adicional"]["id"], cat_b["id"], 100, "2026-09-07").status_code == 404
    # um plástico com portador não aceita segundo convite
    v = a.post(f"/api/plasticos/{s['adicional']['id']}/convites", json={"email": b.email}).json()
    assert b.post(f"/api/convites/{v['id']}/aceitar").status_code == 200
    assert a.post(f"/api/plasticos/{s['adicional']['id']}/convites", json={"email": "outro@x.com"}).status_code == 409


def test_compra_no_cartao_nunca_fica_prevista(nova_pessoa):
    from conftest import conta
    a = nova_pessoa("cartao_prev")
    cc = conta(a, "Corrente", 100000)
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 28, "dia_vencimento": 4,
                                     "conta_pagamento_id": cc["id"], "limite_centavos": 800000, "final_principal": "1111"}).json()
    pl = k["plasticos"][0]["id"]
    t = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 3000, "data_competencia": "2026-09-10",
                                        "plastico_id": pl, "estado": "previsto"}).json()
    assert t[0]["estado"] == "confirmado"                        # pedido de "previsto" é ignorado
    r = a.patch(f"/api/transacoes/{t[0]['id']}", json={"estado": "previsto"})
    assert r.status_code == 200 and r.json()["estado"] == "confirmado"
    # na conta corrente o "previsto" continua valendo
    c = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 500, "data_competencia": "2026-09-10",
                                        "conta_id": cc["id"], "estado": "previsto"}).json()
    assert c[0]["estado"] == "previsto"


def test_cartao_de_uso_proprio(nova_pessoa):
    a, b = nova_pessoa("dono"), nova_pessoa("outro")
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 10, "dia_vencimento": 20,
                                     "final_principal": "1234"}).json()
    assert k["plasticos"][0]["proprio"] is True  # o principal nasce como uso próprio
    ad = a.post(f"/api/cartoes/{k['id']}/plasticos", json={"final": "5678", "rotulo": "Virtual", "tipo": "virtual"}).json()
    assert ad["proprio"] is False
    r = a.patch(f"/api/plasticos/{ad['id']}", json={"proprio": True})
    assert r.status_code == 200, r.text
    assert r.json()["proprio"] is True
    # marcado como seu: não dá para convidar até desmarcar
    assert a.post(f"/api/plasticos/{ad['id']}/convites", json={"email": b.email}).status_code == 409
    assert a.patch(f"/api/plasticos/{ad['id']}", json={"proprio": False}).json()["proprio"] is False
    assert a.post(f"/api/plasticos/{ad['id']}/convites", json={"email": b.email}).status_code == 201
