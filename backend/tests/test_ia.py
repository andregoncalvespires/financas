"""Leitura por IA por pessoa: IA do servidor só para quem o administrador liberar, chave própria cifrada, PDF exige IA."""
import io

import psycopg
from PIL import Image

from app.config import settings
from conftest import OWNER, conta
from test_captura import foto
from test_cartao import cenario  # noqa: F401  (fixture)
from test_fatura_importar import pdf_bytes


def _admin(nova_pessoa, monkeypatch):
    adm = nova_pessoa("admia", ia=False)
    monkeypatch.setattr(settings, "admin_email", adm.email)
    return adm


def test_novo_usuario_nasce_sem_ia_e_o_admin_liga_e_desliga(nova_pessoa, monkeypatch):
    adm, p = _admin(nova_pessoa, monkeypatch), nova_pessoa("semia", ia=False)
    assert p.get("/api/eu").json()["ia"]["modo"] == "nenhum"
    assert adm.get("/api/eu").json()["ia"]["modo"] == "servidor"                   # o administrador sempre pode usar a do servidor
    lista = {u["email"]: u for u in adm.get("/api/admin/usuarios").json()}
    assert lista[p.email]["ia_servidor"] is False and lista[p.email]["chave_propria"] is False
    assert p.post(f"/api/admin/usuarios/{p.id}/ia", json={"liberada": True}).status_code == 403          # só o admin
    assert adm.post(f"/api/admin/usuarios/{p.id}/ia", json={"liberada": True}).json()["ia_servidor"] is True
    assert p.get("/api/eu").json()["ia"]["modo"] == "servidor"
    assert {u["email"]: u for u in adm.get("/api/admin/usuarios").json()}[p.email]["ia_servidor"] is True
    adm.post(f"/api/admin/usuarios/{p.id}/ia", json={"liberada": False})
    assert p.get("/api/eu").json()["ia"]["modo"] == "nenhum"
    assert adm.post("/api/admin/usuarios/00000000-0000-0000-0000-000000000001/ia", json={"liberada": True}).status_code == 404


def test_sem_ia_a_foto_e_guardada_e_o_lancamento_e_manual(nova_pessoa):
    p = nova_pessoa("foto", ia=False)
    r = p.post("/api/capturas", files=foto())
    assert r.status_code == 201, r.text
    cap = r.json()
    assert cap["status"] == "erro" and cap["anexo_id"] and "não ativa" in cap["erro"]
    assert p.get(f"/api/anexos/{cap['anexo_id']}").status_code == 200              # a foto ficou guardada
    c = conta(p, "Corrente", 0)
    ok = p.post(f"/api/capturas/{cap['id']}/confirmar", json={"tipo": "despesa", "valor_centavos": 1234, "data_competencia": "2026-10-01", "conta_id": c["id"],
                                                              "data_caixa": "2026-10-01", "estado": "confirmado", "descricao": "Feito à mão"})
    assert ok.status_code == 201, ok.text


def test_importar_fatura_em_pdf_exige_ia(cenario):  # noqa: F811
    a = cenario["a"]
    from conftest import liberar_ia
    liberar_ia(a, False)
    r = a.post("/api/faturas/importar/ler", data={"cartao_id": cenario["cartao"]["id"]}, files={"arquivo": ("f.pdf", pdf_bytes(), "application/pdf")})
    assert r.status_code == 403 and "IA" in r.json()["detail"]


def test_chave_propria_cifrada_privada_e_sem_limite_diario(nova_pessoa, monkeypatch):
    p, outra = nova_pessoa("chave", ia=False), nova_pessoa("outra", ia=False)
    assert p.put("/api/ia/chave", json={"chave": "curta"}).status_code == 422
    r = p.put("/api/ia/chave", json={"chave": "AIzaSyFAKE_chave_de_teste_1234567890abcd"})
    assert r.status_code == 200 and r.json()["modo"] == "propria" and r.json()["final"] == "abcd"
    assert "chave" not in r.json() and "AIza" not in p.get("/api/eu").text and "AIza" not in p.get("/api/ia").text   # a chave nunca volta
    with psycopg.connect(OWNER) as c:                                                # no banco ela está cifrada
        cif = c.execute("SELECT chave_cifrada FROM usuario_ia WHERE usuario_id = %s", (p.id,)).fetchone()[0]
    assert "AIza" not in cif and len(cif) > 40
    assert outra.get("/api/ia").json()["final"] is None                              # outra pessoa não vê a chave de ninguém
    # sem limite diário com chave própria; com a do servidor o limite vale
    monkeypatch.setattr(settings, "capturas_por_dia", 2)
    for _ in range(3):
        assert p.post("/api/capturas", files=foto()).status_code == 201
    s = nova_pessoa("srv")                                                           # liberada pelo servidor
    assert [s.post("/api/capturas", files=foto()).status_code for _ in range(3)] == [201, 201, 429]
    # remover a chave volta ao estado anterior
    assert p.delete("/api/ia/chave").json()["modo"] == "nenhum"
    assert p.get("/api/ia").json()["final"] is None


def test_admin_ve_origem_do_uso_de_ia(nova_pessoa, monkeypatch):
    adm, p = _admin(nova_pessoa, monkeypatch), nova_pessoa("uso", ia=True)
    p.post("/api/capturas", files=foto()); p.post("/api/capturas", files=foto())
    p.put("/api/ia/chave", json={"chave": "AIzaSyFAKE_chave_de_teste_1234567890wxyz"})
    p.post("/api/capturas", files=foto())
    u = {x["email"]: x for x in adm.get("/api/admin/usuarios").json()}[p.email]
    assert (u["leituras_ia"], u["leituras_servidor_30d"], u["chave_propria"]) == (3, 2, True)
    assert "AIza" not in adm.get("/api/admin/usuarios").text
