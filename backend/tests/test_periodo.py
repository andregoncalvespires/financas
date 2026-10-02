"""Período do resumo por data final (fim de mês) em vez de número de dias."""
from datetime import date, timedelta

from conftest import conta


def test_ate_define_o_periodo_do_resumo_e_dos_eventos(nova_pessoa):
    a = nova_pessoa("periodo")
    cc = conta(a, "Corrente", 100000)
    hoje = date.today()
    perto, longe = hoje + timedelta(days=5), hoje + timedelta(days=120)
    for d, v in ((perto, 1000), (longe, 2000)):
        r = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": v, "data_competencia": d.isoformat(), "conta_id": cc["id"], "estado": "previsto"})
        assert r.status_code == 201, r.text
    corte = (hoje + timedelta(days=30)).isoformat()
    assert a.get(f"/api/saldo-disponivel?ate={corte}").json()["contas"][0]["saidas_previstas"] == -1000
    assert a.get(f"/api/saldo-disponivel?ate={(hoje + timedelta(days=150)).isoformat()}").json()["contas"][0]["saidas_previstas"] == -3000
    l = a.get(f"/api/lembretes?ate={corte}").json()
    assert l["ate"] == corte and l["saidas"] == -1000                         # `ate` vale mais que `dias`
    assert a.get(f"/api/lembretes?dias=7&ate={(hoje + timedelta(days=150)).isoformat()}").json()["saidas"] == -3000
    assert a.get("/api/lembretes?dias=7").json()["saidas"] == -1000           # sem `ate`, continua por dias


def test_ate_muito_distante_e_limitado(nova_pessoa):
    a = nova_pessoa("periodo2")
    conta(a, "Corrente", 0)
    l = a.get("/api/lembretes?ate=2099-01-01").json()
    assert date.fromisoformat(l["ate"]) <= date.today() + timedelta(days=400)
