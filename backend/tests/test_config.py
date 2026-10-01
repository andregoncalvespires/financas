"""Configuração de produção: SMTP obrigatório, segredos gerados e guardados pelo app."""
import os
import smtplib
import stat

import pytest

from app import config, mailer, segredos


@pytest.fixture()
def producao(monkeypatch):
    monkeypatch.delenv("FIN_TESTE", raising=False)
    return monkeypatch


def test_producao_ignora_modo_console(producao):
    producao.setenv("MAIL_MODE", "console")
    assert config.carregar().mail_mode == "smtp"


def test_problemas_lista_o_que_falta(producao):
    for v in ("SMTP_USER", "SMTP_PASSWORD", "APP_PEPPER", "APP_PEPPER_FILE"):
        producao.delenv(v, raising=False)
    faltas = " ".join(config.problemas(config.carregar()))
    for chave in ("APP_PEPPER", "SMTP_USER", "SMTP_PASSWORD"):
        assert chave in faltas
    with pytest.raises(SystemExit) as e:
        producao.setattr(config, "settings", config.carregar())
        config.exigir_configuracao()
    assert "SMTP_PASSWORD" in str(e.value)


def test_configuracao_completa_nao_tem_problemas(producao):
    producao.setenv("SMTP_USER", "a@x.com")
    producao.setenv("SMTP_PASSWORD", "senha")
    producao.setenv("APP_PEPPER", "segredo")
    assert config.problemas(config.carregar()) == []


def test_modo_teste_nao_exige_nada(monkeypatch):
    monkeypatch.setenv("FIN_TESTE", "1")
    monkeypatch.delenv("SMTP_USER", raising=False)
    assert config.problemas(config.carregar()) == []


def test_segredo_prefere_o_arquivo(tmp_path, monkeypatch):
    arq = tmp_path / "pep"
    arq.write_text("do-arquivo\n")
    monkeypatch.setenv("APP_PEPPER", "da-variavel")
    assert config._segredo("APP_PEPPER") == "da-variavel"
    monkeypatch.setenv("APP_PEPPER_FILE", str(arq))
    assert config._segredo("APP_PEPPER") == "do-arquivo"


def test_segredos_sao_gerados_uma_vez_e_nao_mudam(tmp_path):
    r1 = segredos.garantir(str(tmp_path), env={})
    assert set(r1.values()) == {"gerado"} and len(r1) == 3
    antes = {p.name: p.read_text() for p in tmp_path.iterdir()}
    assert all(len(v) >= 48 for v in antes.values()) and len(set(antes.values())) == 3
    assert all(not (p.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)) for p in tmp_path.iterdir())
    r2 = segredos.garantir(str(tmp_path), env={"APP_PEPPER": "outro"})
    assert set(r2.values()) == {"existente"}
    assert {p.name: p.read_text() for p in tmp_path.iterdir()} == antes


def test_instalacao_antiga_tem_os_valores_do_env_adotados(tmp_path):
    env = {"POSTGRES_PASSWORD": "senha-velha-owner", "APP_DB_PASSWORD": "senha-velha-app", "APP_PEPPER": "pepper-velho"}
    r = segredos.garantir(str(tmp_path), env=env)
    assert set(r.values()) == {"adotado do .env"}
    assert (tmp_path / "postgres_password").read_text() == "senha-velha-owner"
    assert (tmp_path / "app_pepper").read_text() == "pepper-velho"


def test_smtp_porta_465_usa_ssl(monkeypatch):
    usado = {}

    class Falso:
        def __init__(self, *a, **k): usado["classe"] = type(self).__name__
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): usado["starttls"] = True
        def login(self, *a): pass
        def send_message(self, m): usado["enviado"] = m["To"]

    class FalsoSSL(Falso): pass
    monkeypatch.setattr(smtplib, "SMTP", Falso)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FalsoSSL)
    monkeypatch.setattr(mailer.settings, "mail_mode", "smtp")
    monkeypatch.setattr(mailer.settings, "smtp_port", 465)
    mailer.enviar("x@y.com", "a", "b")
    assert usado == {"classe": "FalsoSSL", "enviado": "x@y.com"}
    usado.clear()
    monkeypatch.setattr(mailer.settings, "smtp_port", 587)
    mailer.enviar("x@y.com", "a", "b")
    assert usado["classe"] == "Falso" and usado["starttls"]


def test_mail_from_vazio_usa_o_usuario_smtp(monkeypatch):
    monkeypatch.setenv("MAIL_FROM", "")
    monkeypatch.setenv("SMTP_USER", "quem@envia.com")
    assert config.carregar().mail_from == "quem@envia.com"
