"""O administrador (SMTP_USER) recebe um e-mail a cada conta nova, e só na criação."""
from conftest import cliente
from app import mailer
from app.config import settings


def _entrar(app, email):
    c = cliente(app)
    c.post("/api/auth/solicitar", json={"email": email})
    codigo = [m for m in mailer.caixa_saida if m["para"] == email][-1]["corpo"].split("é ")[1][:6]
    assert c.post("/api/auth/verificar", json={"email": email, "codigo": codigo, "dispositivo": "t"}).status_code == 200


def _avisos(email):
    return [m for m in mailer.caixa_saida if m["para"] == "admin@exemplo.com" and email in m["corpo"]]


def test_avisa_admin_so_na_criacao(app_client, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "admin@exemplo.com", raising=False)
    novo = "novato.aviso@exemplo.com"
    _entrar(app_client, novo)
    avisos = _avisos(novo)
    assert len(avisos) == 1 and "novo usuário" in avisos[0]["assunto"].lower()
    _entrar(app_client, novo)                      # segundo acesso (outro dispositivo): não avisa de novo
    assert len(_avisos(novo)) == 1


def test_sem_smtp_user_nao_avisa(app_client, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "", raising=False)
    antes = len(mailer.caixa_saida)
    _entrar(app_client, "sem.aviso@exemplo.com")
    assert not [m for m in mailer.caixa_saida[antes:] if "novo usuário" in m["assunto"].lower()]
