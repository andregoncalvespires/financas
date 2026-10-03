"""Tipos de conta editáveis e recarga mensal de benefícios (ticket/vale)."""
from datetime import date

from conftest import categoria_por_codigo


def tipo_ticket(p, nome="Ticket refeição"):
    r = p.post("/api/tipos-conta", json={"nome": nome, "classe": "beneficio"})
    assert r.status_code == 201, r.text
    return r.json()


def test_tipos_padrao_e_crud(nova_pessoa):
    a, b = nova_pessoa("a"), nova_pessoa("b")
    padrao = {t["nome"] for t in a.get("/api/tipos-conta").json()}
    assert {"Conta corrente", "Investimento", "Ticket / Vale"} <= padrao and "Poupança" not in padrao
    t = tipo_ticket(a)
    assert a.post("/api/tipos-conta", json={"nome": "ticket refeicao", "classe": "corrente"}).status_code == 409
    assert b.patch(f"/api/tipos-conta/{t['id']}", json={"nome": "x"}).status_code == 404       # isolado por usuário
    assert t["id"] not in {x["id"] for x in b.get("/api/tipos-conta").json()}
    r = a.patch(f"/api/tipos-conta/{t['id']}", json={"nome": "Ticket alimentação"})
    assert r.json()["nome"] == "Ticket alimentação"
    c = a.post("/api/contas", json={"nome": "Alelo", "tipo_conta_id": t["id"]}).json()
    assert c["tipo"] == "beneficio" and c["tipo_nome"] == "Ticket alimentação"
    assert a.delete(f"/api/tipos-conta/{t['id']}").status_code == 409                           # em uso
    # mudar o comportamento do tipo vale para as contas
    a.patch(f"/api/tipos-conta/{t['id']}", json={"classe": "corrente"})
    assert [x for x in a.get("/api/contas").json() if x["id"] == c["id"]][0]["tipo"] == "corrente"
    # tipo de outro usuário não pode ser usado
    assert b.post("/api/contas", json={"nome": "x", "tipo_conta_id": t["id"]}).status_code == 422


def test_recarga_mensal_criar_alterar_desativar(nova_pessoa):
    a = nova_pessoa("vr")
    t = tipo_ticket(a)
    hoje = date.today()
    dia = 28 if hoje.day <= 28 else 28
    r = a.post("/api/contas", json={"nome": "VR", "tipo_conta_id": t["id"], "recarga_valor_centavos": 80000, "recarga_dia": dia})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["recarga_valor_centavos"] == 80000 and c["recarga_ativa"] is True and c["saldo_atual"] == 0
    mes = hoje.strftime("%Y-%m")
    fim = (date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1)).isoformat()
    lista = a.get(f"/api/transacoes?conta_id={c['id']}&de={mes}-01&ate={fim}").json()
    previstos = [x for x in lista if x["conta_id"] == c["id"]]
    if hoje.day <= dia:
        assert len(previstos) == 1 and previstos[0]["valor_centavos"] == 80000 and previstos[0]["estado"] == "previsto"
    # alterar valor atualiza previstos; saldo só muda ao confirmar
    r = a.put(f"/api/contas/{c['id']}/recarga", json={"valor_centavos": 90000, "dia_mes": dia, "ativa": True})
    assert r.status_code == 200 and r.json()["recarga_valor_centavos"] == 90000
    lista = [x for x in a.get(f"/api/transacoes?conta_id={c['id']}&de={mes}-01&ate={fim}").json() if x["conta_id"] == c["id"]]
    if hoje.day <= dia:
        assert [x["valor_centavos"] for x in lista] == [90000]
        assert a.post(f"/api/transacoes/{lista[0]['id']}/confirmar").status_code == 200
        assert [x for x in a.get("/api/contas").json() if x["id"] == c["id"]][0]["saldo_atual"] == 90000
        # confirmado não muda quando o padrão muda
        a.put(f"/api/contas/{c['id']}/recarga", json={"valor_centavos": 50000, "dia_mes": dia, "ativa": True})
        lista = [x for x in a.get(f"/api/transacoes?conta_id={c['id']}&de={mes}-01&ate={fim}").json() if x["conta_id"] == c["id"]]
        assert [x["valor_centavos"] for x in lista] == [90000]
    # desativar remove previstos futuros e para de gerar
    r = a.put(f"/api/contas/{c['id']}/recarga", json={"valor_centavos": 50000, "dia_mes": dia, "ativa": False})
    assert r.json()["recarga_ativa"] is False
    lista = [x for x in a.get(f"/api/transacoes?conta_id={c['id']}&de={mes}-01&ate={fim}").json() if x["conta_id"] == c["id"] and x["estado"] == "previsto"]
    assert lista == []
    assert a.post("/api/recorrencias/gerar", json={"mes": mes}).json()["criadas"] == 0
    # reativar volta a gerar (próximo mês, se o dia já passou)
    a.put(f"/api/contas/{c['id']}/recarga", json={"valor_centavos": 50000, "dia_mes": dia, "ativa": True})
    assert [x for x in a.get("/api/contas").json() if x["id"] == c["id"]][0]["recarga_ativa"] is True


def test_recarga_so_em_beneficio_e_permissao(nova_pessoa):
    a, b = nova_pessoa("o"), nova_pessoa("v")
    cc = a.post("/api/contas", json={"nome": "Corrente", "tipo": "corrente"}).json()
    assert a.put(f"/api/contas/{cc['id']}/recarga", json={"valor_centavos": 100, "dia_mes": 5}).status_code == 422
    assert a.post("/api/contas", json={"nome": "x", "tipo": "corrente", "recarga_valor_centavos": 100, "recarga_dia": 5}).status_code == 422
    t = tipo_ticket(a)
    vr = a.post("/api/contas", json={"nome": "VR", "tipo_conta_id": t["id"]}).json()
    assert b.put(f"/api/contas/{vr['id']}/recarga", json={"valor_centavos": 100, "dia_mes": 5}).status_code == 404
    # compatibilidade: criação só com 'tipo'
    assert a.post("/api/contas", json={"nome": "Poup", "tipo": "poupanca"}).json()["tipo_nome"] == "Investimento"


def _previstos_da_conta(p, cid):
    hoje = date.today()
    lista = p.get(f"/api/transacoes?conta_id={cid}&de={hoje.year}-01-01&ate={hoje.year + 1}-12-31&base=caixa&limite=500").json()
    return sorted((x for x in lista if x["conta_id"] == cid), key=lambda x: x["data_caixa"])


def test_recarga_com_competencia_no_mes_seguinte(nova_pessoa):
    a = nova_pessoa("vrc")
    t = tipo_ticket(a)
    r = a.post("/api/contas", json={"nome": "VR", "tipo_conta_id": t["id"], "recarga_valor_centavos": 80000, "recarga_dia": 28, "recarga_competencia_mes": 1})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["recarga_competencia_mes"] == 1
    hoje = date.today()
    a.post("/api/recorrencias/gerar", json={"mes": hoje.strftime("%Y-%m"), "ate": f"{hoje.year + 1}-03"})
    ps = _previstos_da_conta(a, c["id"])
    assert len(ps) >= 5
    for x in ps:
        cx, cp = date.fromisoformat(x["data_caixa"]), date.fromisoformat(x["data_competencia"])
        assert cx.day == 28
        assert cp.day == 1 and (cp.year, cp.month) == ((cx.year + (cx.month == 12)), cx.month % 12 + 1)   # dia 1 do mês seguinte
    # gerar de novo não duplica
    a.post("/api/recorrencias/gerar", json={"mes": date.today().strftime("%Y-%m")})
    assert len(_previstos_da_conta(a, c["id"])) == len(ps)
    # excluir uma ocorrência pula o mês do CAIXA e não volta
    alvo = ps[1]
    assert a.delete(f"/api/transacoes/{alvo['id']}").status_code == 200
    a.post("/api/recorrencias/gerar", json={"mes": alvo["data_caixa"][:7]})
    assert alvo["data_caixa"] not in [x["data_caixa"] for x in _previstos_da_conta(a, c["id"])]
    # voltar para o mesmo mês: competência = caixa
    assert a.put(f"/api/contas/{c['id']}/recarga", json={"valor_centavos": 80000, "dia_mes": 28, "ativa": True, "competencia_mes": 0}).status_code == 200
    novos = _previstos_da_conta(a, c["id"])
    assert novos and all(x["data_competencia"] == x["data_caixa"] for x in novos)


def test_recorrencia_geral_com_competencia_no_mes_anterior(nova_pessoa):
    a = nova_pessoa("sal")
    from conftest import conta
    cc = conta(a, "Corrente", 0)
    r = a.post("/api/recorrencias", json={"tipo": "receita", "valor_centavos": 500000, "dia_mes": 5, "conta_id": cc["id"], "competencia_mes": -1})
    assert r.status_code == 201, r.text
    assert r.json()["competencia_mes"] == -1
    a.post("/api/recorrencias/gerar", json={"mes": date.today().strftime("%Y-%m"), "ate": f"{date.today().year + 1}-03"})
    ps = _previstos_da_conta(a, cc["id"])
    assert ps
    for x in ps:
        cx, cp = date.fromisoformat(x["data_caixa"]), date.fromisoformat(x["data_competencia"])
        assert cx.day == 5 and cp.day == 1 and (cp.year * 12 + cp.month) == (cx.year * 12 + cx.month) - 1
    # no cartão a competência nunca é deslocada
    k = a.post("/api/cartoes", json={"nome": "Visa", "dia_fechamento": 10, "dia_vencimento": 20, "final_principal": "1111"}).json()
    rc = a.post("/api/recorrencias", json={"tipo": "despesa", "valor_centavos": 1000, "dia_mes": 3, "plastico_id": k["plasticos"][0]["id"], "competencia_mes": 1})
    assert rc.status_code == 201 and rc.json()["competencia_mes"] == 0
