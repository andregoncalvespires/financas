"""Testes no nível do banco: conectados como o papel de runtime (sem BYPASSRLS), sem passar pela API."""
import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import APP, categoria_por_codigo, conta


def sql(uid, query, params=None):
    with psycopg.connect(APP, row_factory=dict_row) as c:
        with c.transaction():
            if uid:
                c.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
            cur = c.execute(query, params)
            return cur.fetchall() if cur.description else cur.rowcount


def test_papel_de_runtime_nao_ignora_rls():
    r = sql(None, "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'fin_app'")[0]
    assert r == {"rolsuper": False, "rolbypassrls": False}


def test_usuario_nao_ve_nem_altera_dados_de_outro(nova_pessoa):
    a, b = nova_pessoa("a"), nova_pessoa("b")
    c = conta(a, "Privada", 10000)
    cat = categoria_por_codigo(a, "2020.01")
    a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": 1234, "data_competencia": "2026-09-01",
                                   "conta_id": c["id"], "categoria_id": cat["id"], "favorecido_nome": "Mercado do A"})
    assert len(sql(a.id, "SELECT id FROM transacao")) == 1
    for tabela in ("transacao", "conta", "favorecido", "captura", "anexo", "convite", "dispositivo"):
        assert sql(b.id, f"SELECT 1 FROM {tabela} WHERE " + {"conta": "dono_id", "favorecido": "dono_id"}.get(tabela, "criado_por" if tabela in ("transacao", "captura", "anexo", "convite") else "usuario_id") + " = %s", (a.id,)) == [], tabela
    assert sql(b.id, "SELECT 1 FROM categoria WHERE dono_id = %s", (a.id,)) == []
    assert sql(None, "SELECT 1 FROM transacao") == []          # sem usuário na sessão: nada aparece
    assert sql(None, "SELECT 1 FROM conta") == []
    # B não altera nem apaga
    assert sql(b.id, "UPDATE conta SET nome = 'invadida' WHERE id = %s", (c["id"],)) == 0
    assert sql(b.id, "DELETE FROM conta WHERE id = %s", (c["id"],)) == 0
    # B não insere lançamento na conta de A
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        sql(b.id, """INSERT INTO transacao(criado_por, tipo, valor_centavos, data_competencia, data_caixa, conta_id)
                     VALUES (%s, 'despesa', -1, '2026-09-01', '2026-09-01', %s)""", (b.id, c["id"]))
    # nem se passando por A na coluna criado_por
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        sql(b.id, """INSERT INTO transacao(criado_por, tipo, valor_centavos, data_competencia, data_caixa, conta_id)
                     VALUES (%s, 'despesa', -1, '2026-09-01', '2026-09-01', %s)""", (a.id, c["id"]))


def test_tabelas_de_autenticacao_sao_inacessiveis_diretamente():
    for tabela in ("otp",):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            sql(None, f"SELECT * FROM {tabela}")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        sql(None, "SELECT provisionar_usuario(gen_random_uuid())")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        sql(None, "INSERT INTO usuario(email, nome) VALUES ('x@x.com', 'x')")


def test_usuarios_so_sao_visiveis_quando_ha_relacao(nova_pessoa):
    a, b, c = nova_pessoa("a"), nova_pessoa("b"), nova_pessoa("c")
    assert {str(r["id"]) for r in sql(a.id, "SELECT id FROM usuario")} == {a.id}
    cta = conta(a, "Casa")
    v = a.post(f"/api/contas/{cta['id']}/convites", json={"email": b.email, "papel": "editor"}).json()
    b.post(f"/api/convites/{v['id']}/aceitar")
    assert {str(r["id"]) for r in sql(a.id, "SELECT id FROM usuario")} == {a.id, b.id}
    assert {str(r["id"]) for r in sql(b.id, "SELECT id FROM usuario")} == {a.id, b.id}
    assert {str(r["id"]) for r in sql(c.id, "SELECT id FROM usuario")} == {c.id}
