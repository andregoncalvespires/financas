"""Área de administração: só o e-mail de ADMIN_EMAIL; vazio = ninguém."""
from conftest import conta
from app.config import settings


def test_sem_admin_email_ninguem_acessa(nova_pessoa, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "")
    a = nova_pessoa("adm0")
    assert a.get("/api/admin/usuarios").status_code == 403
    assert a.get("/api/eu").json()["admin"] is False


def test_so_o_admin_ve_a_lista_com_contagens_dos_donos(nova_pessoa, monkeypatch):
    adm, outra = nova_pessoa("adm1"), nova_pessoa("outra")
    monkeypatch.setattr(settings, "admin_email", adm.email.upper())      # maiúsculas/minúsculas não importam
    conta(outra, "Corrente", 1000)
    conta(outra, "Reserva", 0)
    k = outra.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 28, "dia_vencimento": 4,
                                         "conta_pagamento_id": conta(outra, "Pgto", 0)["id"], "limite_centavos": 100000, "final_principal": "1111"})
    assert k.status_code == 201
    assert outra.get("/api/admin/usuarios").status_code == 403
    assert outra.get("/api/eu").json()["admin"] is False
    assert adm.get("/api/eu").json()["admin"] is True
    lista = adm.get("/api/admin/usuarios").json()
    por_email = {u["email"]: u for u in lista}
    u = por_email[outra.email]
    assert (u["contas"], u["cartoes"]) == (3, 1)
    assert u["ultimo_acesso"] and u["criado_em"]
    assert por_email[adm.email]["contas"] == 0
    assert set(u) == {"id", "nome", "email", "criado_em", "ultimo_acesso", "contas", "cartoes",
                      "leituras_ia", "leituras_ia_30d", "lancamentos_por_mes", "ia_servidor", "chave_propria",
                      "leituras_servidor_30d"}   # só contagens: nada de lançamentos ou valores


def test_conta_compartilhada_nao_conta_para_quem_so_participa(nova_pessoa, monkeypatch):
    adm, dona, convidada = nova_pessoa("adm2"), nova_pessoa("dona2"), nova_pessoa("conv2")
    monkeypatch.setattr(settings, "admin_email", adm.email)
    c = conta(dona, "Casa", 0)
    v = dona.post(f"/api/contas/{c['id']}/convites", json={"email": convidada.email, "papel": "leitor"}).json()
    assert convidada.post(f"/api/convites/{v['id']}/aceitar").status_code == 200
    assert any(x["id"] == c["id"] for x in convidada.get("/api/contas").json())       # ela enxerga a conta...
    por_email = {u["email"]: u for u in adm.get("/api/admin/usuarios").json()}
    assert por_email[dona.email]["contas"] == 1 and por_email[convidada.email]["contas"] == 0   # ...mas não conta como dela


def test_marcador_de_ex_usuario_nao_aparece(nova_pessoa, monkeypatch):
    adm = nova_pessoa("adm3")
    monkeypatch.setattr(settings, "admin_email", adm.email)
    assert all(u["email"] != "ex-usuario@invalido.local" for u in adm.get("/api/admin/usuarios").json())


def test_contadores_de_ia_e_lancamentos_por_mes(nova_pessoa, monkeypatch):
    adm, p = nova_pessoa("adm9"), nova_pessoa("uso9")
    monkeypatch.setattr(settings, "admin_email", adm.email)
    c = conta(p, "Corrente", 0)
    antes = {u["email"]: u for u in adm.get("/api/admin/usuarios").json()}[p.email]
    assert (antes["leituras_ia"], antes["leituras_ia_30d"], float(antes["lancamentos_por_mes"])) == (0, 0, 0.0)
    for i in range(6):                                                    # 6 lançamentos manuais
        r = p.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 100 + i, "data_competencia": "2026-10-01", "data_caixa": "2026-10-01",
                                           "conta_id": c["id"], "estado": "confirmado"})
        assert r.status_code == 201, r.text
    p.post("/api/recorrencias", json={"tipo": "despesa", "valor_centavos": 500, "dia_mes": 5, "conta_id": c["id"], "descricao": "Aluguel", "inicio": "2026-10-01"})
    from app.db import sessao
    uid = p.get("/api/eu").json()["id"]                                   # 3 leituras de IA (2 recentes, 1 antiga)
    with sessao(uid) as cur:
        cur.execute("INSERT INTO captura(criado_por, status) VALUES (%s,'descartada'), (%s,'erro')", (uid, uid))
        cur.execute("INSERT INTO captura(criado_por, status, criado_em) VALUES (%s,'descartada', now() - interval '60 days')", (uid,))
    u = {x["email"]: x for x in adm.get("/api/admin/usuarios").json()}[p.email]
    assert (u["leituras_ia"], u["leituras_ia_30d"]) == (3, 2)
    assert float(u["lancamentos_por_mes"]) == 6.0                         # conta recém-criada: divide por 1 mês; recorrência não conta
