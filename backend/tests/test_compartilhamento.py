from conftest import categoria_por_codigo, conta


def tx(p, cid, cat, valor=5000, **extra):
    return p.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": valor, "data_competencia": "2026-09-01",
                                          "conta_id": cid, "categoria_id": cat, **extra})


def test_compartilhar_conta_por_convite(nova_pessoa):
    a, b, estranho = nova_pessoa("a"), nova_pessoa("b"), nova_pessoa("x")
    conj = conta(a, "Conjunta", 100000)
    conta(a, "Privada", 50000)
    cat_a = categoria_por_codigo(a, "2020.01")

    v = a.post(f"/api/contas/{conj['id']}/convites", json={"email": b.email, "papel": "leitor"}).json()
    assert b.get("/api/contas").json() == []                                   # antes de aceitar, nada é visível
    rec = b.get("/api/convites").json()["recebidos"]
    assert len(rec) == 1 and rec[0]["descricao"] == "Conta Conjunta" and rec[0]["convidado_por_nome"]
    assert estranho.post(f"/api/convites/{v['id']}/aceitar").status_code == 400   # convite é do e-mail de B
    assert b.post(f"/api/convites/{v['id']}/aceitar").status_code == 200

    contas_b = b.get("/api/contas").json()
    assert [c["nome"] for c in contas_b] == ["Conjunta"] and contas_b[0]["papel"] == "leitor"   # a Privada continua invisível
    assert contas_b[0]["saldo_atual"] == 100000

    assert tx(a, conj["id"], cat_a["id"]).status_code == 201
    assert len(b.get("/api/transacoes").json()) == 1
    assert tx(b, conj["id"], cat_a["id"]).status_code == 403                    # leitor não lança

    # A troca o papel de B para editor (novo convite aceito substitui o papel)
    assert a.delete(f"/api/contas/{conj['id']}/acessos/{b.id}").status_code == 200
    assert b.get("/api/contas").json() == []
    v2 = a.post(f"/api/contas/{conj['id']}/convites", json={"email": b.email, "papel": "editor"}).json()
    assert b.post(f"/api/convites/{v2['id']}/aceitar").status_code == 200

    r = tx(b, conj["id"], cat_a["id"], 7000, favorecido_nome="Padaria")
    assert r.status_code == 201, r.text
    assert r.json()[0]["criado_por"] == b.id
    assert any(t["criado_por_nome"] for t in a.get("/api/transacoes").json())
    # cadastros válidos são os do dono da conta: a categoria de B é recusada
    cat_b = categoria_por_codigo(b, "2020.01", dono_id=b.id)
    assert tx(b, conj["id"], cat_b["id"]).status_code == 422

    # editor não gerencia
    assert b.delete(f"/api/contas/{conj['id']}").status_code == 404
    assert b.post(f"/api/contas/{conj['id']}/convites", json={"email": estranho.email}).status_code == 403
    assert b.patch(f"/api/contas/{conj['id']}", json={"nome": "X"}).status_code == 404
    # o favorecido criado por B fica no cadastro de A
    assert any(f["nome"] == "Padaria" and f["dono_id"] == a.id for f in a.get("/api/favorecidos").json())

    # B sai da conta
    assert b.delete(f"/api/contas/{conj['id']}/acessos/{b.id}").status_code == 200
    assert b.get("/api/contas").json() == [] and b.get("/api/transacoes").json() == []


def test_transferencia_entre_conta_privada_e_conjunta_nao_expoe_a_origem(nova_pessoa):
    a, b = nova_pessoa("a"), nova_pessoa("b")
    conj, priv = conta(a, "Conjunta"), conta(a, "Privada", 90000)
    v = a.post(f"/api/contas/{conj['id']}/convites", json={"email": b.email, "papel": "editor"}).json()
    b.post(f"/api/convites/{v['id']}/aceitar")
    r = a.post("/api/transferencias", json={"conta_origem_id": priv["id"], "conta_destino_id": conj["id"], "valor_centavos": 10000, "data": "2026-09-02"})
    assert r.status_code == 201, r.text
    vistas = b.get("/api/transacoes").json()
    assert len(vistas) == 1 and vistas[0]["conta_id"] == conj["id"] and vistas[0]["valor_centavos"] == 10000
    assert priv["id"] not in str(vistas)
    assert b.delete(f"/api/transacoes/{vistas[0]['id']}").status_code == 403    # não pode apagar só um lado
    assert len(a.get("/api/transacoes").json()) == 2
    saldo = {c["nome"]: c["saldo_atual"] for c in a.get("/api/contas").json()}
    assert saldo == {"Conjunta": 10000, "Privada": 80000}
    assert a.delete(f"/api/transacoes/{vistas[0]['id']}").status_code == 200    # dono apaga os dois lados
    assert a.get("/api/transacoes").json() == []


def test_limite_diario_de_convites(nova_pessoa):
    import uuid
    a = nova_pessoa("lim")
    c = a.post("/api/contas", json={"nome": "Casa"}).json()
    codigos = [a.post(f"/api/contas/{c['id']}/convites", json={"email": f"x{i}-{uuid.uuid4().hex[:5]}@teste.com", "papel": "leitor"}).status_code for i in range(21)]
    assert codigos[:20] == [201] * 20 and codigos[20] == 429
