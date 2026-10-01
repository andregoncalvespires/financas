"""Importação de fatura em PDF (IA simulada, dados fictícios): casamento com o que já existe, diferença de valor, aplicar."""
import io

import pikepdf
import pytest

from app import gemini
from conftest import categoria_por_codigo, conta


def pdf_bytes(senha=None):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    saida = io.BytesIO()
    if senha:
        pdf.save(saida, encryption=pikepdf.Encryption(owner=senha, user=senha))
    else:
        pdf.save(saida)
    return saida.getvalue()


FATURA = {
    "emissor": "Banco Exemplo", "vencimento": "2026-10-04", "fechamento": "2026-09-28", "total_fatura": 500.0,
    "linhas": [
        {"data": "2026-09-01", "descricao": "SUPERMERCADOS BH", "valor": 120.00, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "compra"},
        {"data": "2026-09-05", "descricao": "PADARIA MERCAPAO", "valor": 34.33, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "compra"},
        {"data": "2026-09-10", "descricao": "DL *UBERRIDES", "valor": 8.94, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "compra"},
        {"data": "2026-09-12", "descricao": "ANTHROPIC", "valor": 53.09, "valor_usd": 9.70, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "compra"},
        {"data": "2026-09-12", "descricao": "IOF DESPESA NO EXTERIOR", "valor": 1.86, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "iof_exterior"},
        {"data": "2026-08-15", "descricao": "LOJA XYZ", "valor": 100.00, "parcela_atual": 3, "parcelas_total": 10, "final_cartao": "1111", "tipo": "compra"},
        {"data": "2026-09-20", "descricao": "LOJA ABC", "valor": -20.00, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "estorno_credito"},
        {"data": "2026-09-02", "descricao": "PAGAMENTO FATURA", "valor": -500.00, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "pagamento"},
        {"data": "2026-09-28", "descricao": "JUROS", "valor": 12.00, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "1111", "tipo": "encargo"},
        {"data": "2026-09-22", "descricao": "POSTO CENTRAL", "valor": 200.00, "parcela_atual": 1, "parcelas_total": 1, "final_cartao": "2222", "tipo": "compra"},
    ],
}


@pytest.fixture()
def cenario(nova_pessoa):
    a = nova_pessoa("fat")
    cc = conta(a, "Corrente", 900000)
    k = a.post("/api/cartoes", json={"nome": "Visa", "bandeira": "visa", "dia_fechamento": 28, "dia_vencimento": 4,
                                     "conta_pagamento_id": cc["id"], "limite_centavos": 800000, "final_principal": "1111"}).json()
    ad = a.post(f"/api/cartoes/{k['id']}/plasticos", json={"final": "2222", "rotulo": "Adicional"}).json()
    principal = next(p for p in k["plasticos"] if p["final"] == "1111")
    cat = categoria_por_codigo(a, "2020.01")
    def compra(valor, data, fav):
        r = a.post("/api/transacoes", json={"tipo": "despesa", "valor_centavos": valor, "data_competencia": data, "plastico_id": principal["id"],
                                            "categoria_id": cat["id"], "favorecido_nome": fav})
        assert r.status_code == 201, r.text
        return r.json()[0]
    existentes = dict(mercado=compra(12000, "2026-09-01", "Supermercados BH"), padaria=compra(3000, "2026-09-05", "Padaria Mercapao"),
                      cinema=compra(5000, "2026-09-25", "Cinema"))
    return dict(a=a, k=k, principal=principal, adicional=ad, cat=cat, ex=existentes)


def ler(a, k, senha="", dados=None):
    gemini.MOCK_FATURA = FATURA
    return a.post("/api/faturas/importar/ler", files={"arquivo": ("f.pdf", dados or pdf_bytes(), "application/pdf")}, data={"cartao_id": k["id"], "senha": senha})


def test_previa_casa_o_que_existe_e_mostra_a_diferenca(cenario):
    a, k = cenario["a"], cenario["k"]
    r = ler(a, k)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["fatura"]["vencimento"] == "2026-10-04" and p["fatura"]["total_centavos"] == 50000
    L = {l["descricao"]: l for l in p["linhas"]}
    assert L["SUPERMERCADOS BH"]["casamento"]["diferenca_centavos"] == 0 and L["SUPERMERCADOS BH"]["acao_sugerida"] == "conferir"
    pad = L["PADARIA MERCAPAO"]
    assert pad["casamento"]["valor_centavos"] == 3000 and pad["casamento"]["diferenca_centavos"] == 433 and pad["acao_sugerida"] == "atualizar"
    assert L["DL *UBERRIDES"]["acao_sugerida"] == "criar" and L["DL *UBERRIDES"]["favorecido_nome"] == "Uberrides"
    assert L["ANTHROPIC"]["valor_centavos"] == 5495 and L["ANTHROPIC"]["iof_centavos"] == 186        # IOF somado à compra
    assert "IOF DESPESA NO EXTERIOR" not in L
    assert L["PAGAMENTO FATURA"]["acao_sugerida"] == "ignorar" and L["JUROS"]["acao_sugerida"] == "ignorar"
    assert L["LOJA ABC"]["eh_credito"] is True
    assert L["POSTO CENTRAL"]["plastico_id"] == cenario["adicional"]["id"]
    assert [x["descricao"] for x in p["no_app_sem_par"]] == ["Cinema"]
    assert p["fatura"]["soma_compras_centavos"] == 12000 + 3433 + 894 + 5495 + 10000 - 2000 + 20000


def test_senha_do_pdf(cenario):
    a, k = cenario["a"], cenario["k"]
    protegido = pdf_bytes("segredo")
    assert ler(a, k, "", protegido).status_code == 422
    assert ler(a, k, "errada", protegido).status_code == 422
    assert ler(a, k, "segredo", protegido).status_code == 200
    assert ler(a, k, "", b"nao e pdf").status_code == 415


def test_aplicar_cria_atualiza_e_nao_duplica(cenario):
    a, k = cenario["a"], cenario["k"]
    p = ler(a, k).json()
    linhas = []
    for l in p["linhas"]:
        o = {"acao": l["acao_sugerida"], "transacao_id": (l.get("casamento") or {}).get("transacao_id"), "data": l["data"], "descricao": l["descricao"],
             "favorecido_nome": l["favorecido_nome"], "favorecido_id": l["favorecido_id"], "categoria_id": l["categoria_id"], "plastico_id": l["plastico_id"],
             "valor_centavos": l["valor_centavos"], "eh_credito": l["eh_credito"], "parcela_atual": l["parcela_atual"], "parcelas_total": l["parcelas_total"], "criar_futuras": l["parcelas_total"] > l["parcela_atual"]}
        linhas.append(o)
    r = a.post("/api/faturas/importar/aplicar", json={"cartao_id": k["id"], "vencimento": "2026-10-04", "linhas": linhas})
    assert r.status_code == 200, r.text
    assert r.json()["criadas"] == 5 and r.json()["atualizadas"] == 1 and r.json()["futuras"] == 7
    por_desc = {t["descricao"] or t["favorecido_nome"]: t for t in a.get("/api/transacoes", params={"cartao_id": k["id"], "limite": 100}).json()}
    pad = cenario["ex"]["padaria"]
    atual = next(t for t in a.get("/api/transacoes", params={"cartao_id": k["id"], "limite": 100}).json() if t["id"] == pad["id"])
    assert atual["valor_centavos"] == -3433
    parc = por_desc["LOJA XYZ"]
    assert parc["numero_parcela"] == 3 and parc["total_parcelas"] == 10 and parc["data_caixa"] == "2026-10-04" and parc["data_competencia"] == "2026-10-15"
    assert por_desc["LOJA ABC"]["valor_centavos"] == 2000 and por_desc["LOJA ABC"]["tipo"] == "receita"
    assert por_desc["ANTHROPIC"]["valor_centavos"] == -5495 and por_desc["ANTHROPIC"]["origem"] == "fatura"
    assert por_desc["POSTO CENTRAL"]["plastico_id"] == cenario["adicional"]["id"]
    # ler de novo: tudo já está lançado, nada novo a criar
    p2 = ler(a, k).json()
    assert [l["descricao"] for l in p2["linhas"] if l["acao_sugerida"] == "criar"] == []
    assert not [l for l in p2["linhas"] if l["acao_sugerida"] == "atualizar"]


def test_so_o_dono_importa_e_vencimento_incompativel(cenario, nova_pessoa):
    a, k = cenario["a"], cenario["k"]
    outro = nova_pessoa("intruso")
    assert ler(outro, k).status_code == 403
    r = a.post("/api/faturas/importar/aplicar", json={"cartao_id": k["id"], "vencimento": "2026-10-09", "linhas": [
        {"acao": "criar", "data": "2026-09-10", "descricao": "X", "valor_centavos": 100, "plastico_id": cenario["principal"]["id"]}]})
    assert r.status_code == 422 and "não bate" in r.json()["detail"]


def test_parcelas_futuras_previstas_nao_mexem_na_fatura_atual_e_confirmam_na_proxima(cenario):
    a, k = cenario["a"], cenario["k"]
    p = ler(a, k).json()
    linhas = [{"acao": "criar", "data": l["data"], "descricao": l["descricao"], "favorecido_nome": l["favorecido_nome"], "plastico_id": l["plastico_id"],
               "valor_centavos": l["valor_centavos"], "parcela_atual": l["parcela_atual"], "parcelas_total": l["parcelas_total"], "criar_futuras": True}
              for l in p["linhas"] if l["descricao"] == "LOJA XYZ"]
    r = a.post("/api/faturas/importar/aplicar", json={"cartao_id": k["id"], "vencimento": "2026-10-04", "linhas": linhas}).json()
    assert r["criadas"] == 1 and r["futuras"] == 7
    fats = {f["data_vencimento"]: f for f in a.get(f"/api/cartoes/{k['id']}/faturas").json()}
    assert fats["2026-10-04"]["total"] == -(12000 + 3000 + 5000 + 10000)             # a fatura atual só ganhou a parcela 3/10
    assert fats["2026-11-04"]["total"] == -10000 and fats["2027-05-04"]["total"] == -10000   # parcelas 4/10 e 10/10, nos meses certos
    parcelas = [t for t in a.get("/api/transacoes", params={"cartao_id": k["id"], "limite": 100}).json() if t["descricao"] == "LOJA XYZ"]
    assert sorted(t["numero_parcela"] for t in parcelas) == list(range(3, 11))
    assert {t["estado"] for t in parcelas if t["numero_parcela"] > 3} == {"previsto"}
    assert len({t["parcelamento_id"] for t in parcelas}) == 1
    # aplicar de novo com as futuras marcadas não duplica
    outro = a.post("/api/faturas/importar/aplicar", json={"cartao_id": k["id"], "vencimento": "2026-10-04", "linhas": linhas}).json()
    assert outro["futuras"] == 0                                                   # as parcelas seguintes já existem: não duplica
    # fatura seguinte: a parcela 4/10 casa com a prevista e passa a confirmada
    gemini.MOCK_FATURA = {"emissor": "Banco Exemplo", "vencimento": "2026-11-04", "fechamento": "2026-10-28", "total_fatura": 100.0, "linhas": [
        {"data": "2026-08-15", "descricao": "LOJA XYZ", "valor": 100.00, "parcela_atual": 4, "parcelas_total": 10, "final_cartao": "1111", "tipo": "compra"}]}
    q = a.post("/api/faturas/importar/ler", files={"arquivo": ("f.pdf", pdf_bytes(), "application/pdf")}, data={"cartao_id": k["id"], "senha": ""}).json()
    l = q["linhas"][0]
    assert l["acao_sugerida"] == "conferir" and l["casamento"]["diferenca_centavos"] == 0
    a.post("/api/faturas/importar/aplicar", json={"cartao_id": k["id"], "vencimento": "2026-11-04", "linhas": [
        {"acao": "conferir", "transacao_id": l["casamento"]["transacao_id"], "data": l["data"], "descricao": l["descricao"], "plastico_id": l["plastico_id"],
         "valor_centavos": l["valor_centavos"], "parcela_atual": 4, "parcelas_total": 10}]})
    t4 = next(t for t in a.get("/api/transacoes", params={"cartao_id": k["id"], "limite": 100}).json() if t["descricao"] == "LOJA XYZ" and t["numero_parcela"] == 4)
    assert t4["estado"] == "confirmado"
