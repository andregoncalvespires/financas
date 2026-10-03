import os
import tempfile
import uuid
from dataclasses import dataclass

import psycopg
import pytest

OWNER = "postgresql://fin_owner:owner_dev@localhost/financas_test"
APP = "postgresql://fin_app:app_dev@localhost/financas_test"
os.environ.update(
    DATABASE_URL=APP, DATABASE_URL_OWNER=OWNER, APP_DB_PASSWORD="app_dev", MAIL_MODE="console", FIN_TESTE="1",
    GEMINI_MOCK="1", DADOS_DIR=tempfile.mkdtemp(prefix="fin_dados_"), APP_PEPPER="teste",
)

from fastapi.testclient import TestClient  # noqa: E402

from app import mailer  # noqa: E402
from app.config import settings  # noqa: E402
from app.migrate import aplicar  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def banco():
    with psycopg.connect(OWNER, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
        c.execute("DROP TABLE IF EXISTS schema_migracao")
    aplicar(OWNER, "app_dev")
    yield


@pytest.fixture(scope="session")
def app_client():
    from app.main import app
    with TestClient(app) as _:
        yield app


@dataclass
class Pessoa:
    email: str
    c: TestClient
    id: str = ""

    def get(self, *a, **k): return self.c.get(*a, **k)
    def post(self, *a, **k): return self.c.post(*a, **k)
    def patch(self, *a, **k): return self.c.patch(*a, **k)
    def put(self, *a, **k): return self.c.put(*a, **k)
    def delete(self, *a, **k): return self.c.delete(*a, **k)


def cliente(app, x_fin=True) -> TestClient:
    """Cada cliente tem um IP distinto (cabeçalho de proxy), para não esbarrar no limite de pedidos por IP."""
    h = {"X-Forwarded-For": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}
    if x_fin:
        h["X-Fin"] = "1"
    return TestClient(app, headers=h)


def liberar_ia(p, liberada=True):
    """Liga/desliga a IA do servidor para uma pessoa de teste (o administrador faz isso pela API)."""
    with psycopg.connect(OWNER, autocommit=True) as c:
        c.execute("UPDATE usuario SET ia_servidor = %s WHERE id = %s", (liberada, p.id))


def _login(app, email: str) -> Pessoa:
    c = cliente(app)
    assert c.post("/api/auth/solicitar", json={"email": email}).status_code == 202
    codigo = [m for m in mailer.caixa_saida if m["para"] == email][-1]["corpo"].split("é ")[1][:6]
    r = c.post("/api/auth/verificar", json={"email": email, "codigo": codigo, "dispositivo": "teste"})
    assert r.status_code == 200, r.text
    p = Pessoa(email, c)
    p.id = c.get("/api/eu").json()["id"]
    return p


@pytest.fixture()
def nova_pessoa(app_client):
    def criar(prefixo="u", ia=True) -> Pessoa:
        p = _login(app_client, f"{prefixo}-{uuid.uuid4().hex[:8]}@teste.com")
        if ia:
            liberar_ia(p)                       # a maioria dos testes usa a leitura por IA; os de liberação pedem ia=False
        return p
    return criar


@pytest.fixture()
def dono(nova_pessoa):
    return nova_pessoa("dono")


def conta(p, nome="Corrente", saldo=0, tipo="corrente"):
    r = p.post("/api/contas", json={"nome": nome, "tipo": tipo, "saldo_inicial_centavos": saldo, "data_saldo_inicial": "2026-01-01"})
    assert r.status_code == 201, r.text
    return r.json()


def categoria_por_codigo(p, codigo, dono_id=None):
    cats = p.get("/api/categorias").json()
    return next(c for c in cats if c["codigo_origem"] == codigo and (dono_id is None or c["dono_id"] == dono_id))
