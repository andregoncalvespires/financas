import uuid

from fastapi.testclient import TestClient

from conftest import cliente
from app import mailer
from app.config import settings


def test_login_lembra_dispositivo_e_exige_cabecalho(nova_pessoa, app_client):
    p = nova_pessoa()
    assert p.get("/api/eu").json()["email"] == p.email
    # escrita via cookie sem X-Fin é recusada (CSRF)
    c2 = cliente(app_client, x_fin=False)
    c2.cookies.update(p.c.cookies)
    assert c2.post("/api/contas", json={"nome": "x"}).status_code == 403
    assert c2.get("/api/eu").status_code == 200


def test_kit_de_categorias_copiado_no_primeiro_acesso(nova_pessoa):
    p = nova_pessoa()
    cats = p.get("/api/categorias").json()
    assert len(cats) >= 95 and {c["dono_id"] for c in cats} == {p.id}
    assert any(c["codigo_origem"] == "2020.01" and c["nome"] == "Supermercado" for c in cats)


def test_sair_revoga_e_dispositivos_podem_ser_revogados(nova_pessoa, app_client):
    p = nova_pessoa()
    # segundo dispositivo do mesmo usuário
    c2 = cliente(app_client)
    c2.post("/api/auth/solicitar", json={"email": p.email})
    cod = [m for m in mailer.caixa_saida if m["para"] == p.email][-1]["corpo"].split("é ")[1][:6]
    assert c2.post("/api/auth/verificar", json={"email": p.email, "codigo": cod, "dispositivo": "celular"}).status_code == 200
    disp = p.get("/api/dispositivos").json()
    assert len(disp) == 2 and sum(d["atual"] for d in disp) == 1
    outro = next(d for d in disp if not d["atual"])
    assert p.delete(f"/api/dispositivos/{outro['id']}").status_code == 200
    assert c2.get("/api/eu").status_code == 401
    assert p.post("/api/auth/sair").status_code == 200
    assert p.get("/api/eu").status_code == 401


def test_codigo_errado_bloqueia_apos_tentativas(app_client):
    c = cliente(app_client)
    email = f"x-{uuid.uuid4().hex[:6]}@teste.com"
    c.post("/api/auth/solicitar", json={"email": email})
    cods = [c.post("/api/auth/verificar", json={"email": email, "codigo": "000000"}).status_code for _ in range(6)]
    assert cods[:5] == [400] * 5 and cods[5] == 429
    real = [m for m in mailer.caixa_saida if m["para"] == email][-1]["corpo"].split("é ")[1][:6]
    assert c.post("/api/auth/verificar", json={"email": email, "codigo": real}).status_code == 429  # mesmo o certo, após bloqueio


def test_limite_de_solicitacoes_por_email(app_client):
    c = cliente(app_client, x_fin=False)
    email = f"y-{uuid.uuid4().hex[:6]}@teste.com"
    st = [c.post("/api/auth/solicitar", json={"email": email}).status_code for _ in range(6)]
    assert st[:5] == [202] * 5 and st[5] == 429


def test_qualquer_e_mail_entra_provando_o_codigo(app_client):
    c = cliente(app_client)
    novo = f"n-{uuid.uuid4().hex[:6]}@teste.com"
    antes = len(mailer.caixa_saida)
    assert c.post("/api/auth/solicitar", json={"email": novo}).status_code == 202
    assert len(mailer.caixa_saida) == antes + 1                                          # sem lista de e-mails: o código é a prova
    cod = mailer.caixa_saida[-1]["corpo"].split("é ")[1][:6]
    assert c.post("/api/auth/verificar", json={"email": novo, "codigo": "000000"}).status_code == 400
    assert c.post("/api/auth/verificar", json={"email": novo, "codigo": cod}).status_code == 200
    assert c.get("/api/eu").json()["email"] == novo


def test_cookie_de_sessao_e_seguro_somente_em_https(app_client):
    from starlette.testclient import TestClient
    for base, esperado in (("http://testserver", False), ("https://testserver", True)):
        email = f"s-{uuid.uuid4().hex[:6]}@teste.com"
        c = TestClient(app_client, base_url=base, headers={"X-Fin": "1", "X-Forwarded-For": f"10.9.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"})
        c.post("/api/auth/solicitar", json={"email": email})
        cod = [m for m in mailer.caixa_saida if m["para"] == email][-1]["corpo"].split("é ")[1][:6]
        r = c.post("/api/auth/verificar", json={"email": email, "codigo": cod})
        assert ("secure" in r.headers["set-cookie"].lower()) is esperado
