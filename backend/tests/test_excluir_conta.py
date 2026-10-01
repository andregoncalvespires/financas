"""Exclusão da própria conta + versão do app."""
import io
import re
import zipfile

import psycopg
from conftest import OWNER, categoria_por_codigo, conta
from app import mailer


def compartilha(dono, outro, c, papel="editor"):
    v = dono.post(f"/api/contas/{c['id']}/convites", json={"email": outro.email, "papel": papel}).json()
    assert outro.post(f"/api/convites/{v['id']}/aceitar").status_code in (200, 201)


def codigo_exclusao(p):
    assert p.post("/api/conta/exclusao/codigo").status_code == 202
    msg = [m for m in mailer.caixa_saida if m["para"] == p.email][-1]["corpo"]
    assert "EXCLUIR" in msg
    return re.search(r"\b(\d{6})\b", msg).group(1)


def saldos(p):
    return {c["nome"]: c["saldo_atual"] for c in p.get("/api/contas").json()}


def test_versao_e_publica(app_client):
    from conftest import cliente
    r = cliente(app_client).get("/api/versao")
    assert r.status_code == 200 and re.match(r"^\d+\.\d+\.\d+$", r.json()["versao"])
    assert r.json()["historico"] and r.json()["historico"][0]["itens"]


def test_exclusao_exige_confirmacao_e_codigo(nova_pessoa):
    a = nova_pessoa("x1")
    cod = codigo_exclusao(a)
    assert a.c.request("DELETE", "/api/conta", json={"confirmacao": "talvez", "codigo": cod}).status_code == 422
    assert a.c.request("DELETE", "/api/conta", json={"confirmacao": "EXCLUIR", "codigo": "000000"}).status_code == 400
    assert a.get("/api/eu").status_code == 200                                         # nada foi apagado


def test_exclusao_apaga_tudo_do_dono_e_preserva_o_dos_outros(nova_pessoa):
    a, b = nova_pessoa("ea"), nova_pessoa("eb")
    cat_a = categoria_por_codigo(a, "2020.01")
    ac = conta(a, "A conjunta", 100000)                    # de A, compartilhada com B
    priv = conta(a, "A privada", 50000)
    bc = conta(b, "B corrente", 80000)                     # de B, A é editor
    compartilha(a, b, ac)
    compartilha(b, a, bc)
    cat_b = categoria_por_codigo(b, "2020.01")
    # A lança na conta de B (deve sobreviver) e em contas suas (devem sumir)
    assert a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 3000, "data_competencia": "2026-09-05", "conta_id": bc["id"], "descricao": "feito pela A"}).status_code == 201
    assert a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 1000, "data_competencia": "2026-09-05", "conta_id": ac["id"], "categoria_id": cat_a["id"]}).status_code == 201
    assert b.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 2000, "data_competencia": "2026-09-06", "conta_id": ac["id"]}).status_code == 201
    # transferência efetivada entre a conta de A e a de B
    assert a.post("/api/transferencias", json={"conta_origem_id": ac["id"], "conta_destino_id": bc["id"], "valor_centavos": 7000, "data": "2026-09-07"}).status_code == 201
    # transferência prevista idem (a ponta de B deve sumir)
    assert a.post("/api/transferencias", json={"conta_origem_id": ac["id"], "conta_destino_id": bc["id"], "valor_centavos": 500, "data": "2026-10-07", "estado": "previsto"}).status_code == 201
    saldo_b_antes = saldos(b)["B corrente"]
    assert saldo_b_antes == 80000 - 3000 + 7000

    r = a.get("/api/conta/exclusao").json()
    assert "A conjunta" in r["compartilhadas"] and "A privada" not in r["compartilhadas"]
    assert [c["outros"] for c in r["contas"] if c["nome"] == "A conjunta"][0] == [b.c.get("/api/eu").json()["nome"]]

    cod = codigo_exclusao(a)
    r = a.c.request("DELETE", "/api/conta", json={"confirmacao": "excluir", "codigo": cod})
    assert r.status_code == 200, r.text
    assert a.get("/api/eu").status_code == 401                                          # sessão encerrada

    # B continua com o que é dele
    assert set(saldos(b)) == {"B corrente"}                                              # conta compartilhada da A sumiu para B
    assert saldos(b)["B corrente"] == saldo_b_antes                                      # saldo preservado, inclusive a transferência efetivada
    lanc = b.get("/api/transacoes?limite=100").json()
    assert {t["descricao"] for t in lanc if t["descricao"]} >= {"feito pela A"}
    assert all(t["estado"] != "previsto" for t in lanc)                                  # ponta prevista da transferência sumiu
    assert any(t["tipo"] == "transferencia" and t["contraparte_nome"] is None for t in lanc)
    assert {t["descricao"]: t for t in lanc if t["descricao"]}["feito pela A"]["criado_por_nome"] == "Ex-usuário"
    with psycopg.connect(OWNER, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM usuario WHERE email = %s", (a.email,)).fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM conta WHERE nome IN ('A conjunta','A privada')").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM categoria WHERE dono_id = %s", (a.id,)).fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM transacao WHERE criado_por = %s", (a.id,)).fetchone()[0] == 0

    # mesma pessoa pode voltar do zero
    from conftest import _login
    novo = _login(a.c.app if hasattr(a.c, "app") else b.c.app, a.email)
    assert saldos(novo) == {}


def test_exclusao_remove_comprovante_sem_uso_e_mantem_o_compartilhado(nova_pessoa):
    a, b = nova_pessoa("ca"), nova_pessoa("cb")
    bc = conta(b, "B corrente")
    compartilha(b, a, bc)
    cat_b = categoria_por_codigo(b, "2020.01")
    t_b = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 100, "data_competencia": "2026-09-05", "conta_id": bc["id"]}).json()[0]
    ac = conta(a, "A privada")
    cat_a = categoria_por_codigo(a, "2020.01", a.id)
    t_a = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 200, "data_competencia": "2026-09-05", "conta_id": ac["id"], "categoria_id": cat_a["id"]}).json()[0]
    from app.config import settings
    from pathlib import Path
    base = Path(settings.dados_dir)
    (base / "anexos").mkdir(exist_ok=True)
    (base / "anexos" / "sem_uso.bin").write_bytes(b"x")
    (base / "anexos" / "compartilhado.bin").write_bytes(b"y")
    with psycopg.connect(OWNER, autocommit=True) as c:
        ids = {}
        for nome, tx in (("sem_uso.bin", t_a["id"]), ("compartilhado.bin", t_b["id"])):
            ids[nome] = c.execute("INSERT INTO anexo(criado_por, caminho, mime, sha256, tamanho) VALUES (%s,%s,'image/png','h',1) RETURNING id", (a.id, f"anexos/{nome}")).fetchone()[0]
            c.execute("UPDATE transacao SET anexo_id = %s WHERE id = %s", (ids[nome], tx))
    zip_ = a.get("/api/exportar/completo")
    assert zip_.status_code == 200 and "financas_completo.xlsx" in zipfile.ZipFile(io.BytesIO(zip_.content)).namelist()
    assert a.c.request("DELETE", "/api/conta", json={"confirmacao": "EXCLUIR", "codigo": codigo_exclusao(a)}).status_code == 200
    assert not (base / "anexos" / "sem_uso.bin").exists()
    assert (base / "anexos" / "compartilhado.bin").exists()
    with psycopg.connect(OWNER, autocommit=True) as c:
        assert c.execute("SELECT criado_por FROM anexo WHERE id = %s", (ids["compartilhado.bin"],)).fetchone()[0] != a.id
        assert c.execute("SELECT count(*) FROM anexo WHERE id = %s", (ids["sem_uso.bin"],)).fetchone()[0] == 0


def test_exclusao_de_dono_de_cartao_compartilhado(nova_pessoa):
    a, b = nova_pessoa("ka"), nova_pessoa("kb")
    cc = conta(a, "Corrente A", 100000)
    k = a.post("/api/cartoes", json={"nome": "Visa A", "dia_fechamento": 5, "dia_vencimento": 15, "conta_pagamento_id": cc["id"], "final": "1234"})
    assert k.status_code == 201, k.text
    kid = k.json()["id"]
    assert a.get("/api/conta/exclusao").json()["cartoes"][0]["nome"] == "Visa A"
    assert a.c.request("DELETE", "/api/conta", json={"confirmacao": "EXCLUIR", "codigo": codigo_exclusao(a)}).status_code == 200
    with psycopg.connect(OWNER, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM cartao WHERE id = %s", (kid,)).fetchone()[0] == 0
    assert b.get("/api/eu").status_code == 200


def test_versao_do_app_web_confere_com_arquivo_version():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[2]
    web = (raiz / "web" / "js" / "versao.js").read_text()
    assert f"'{(raiz / 'VERSION').read_text().strip()}'" in web
