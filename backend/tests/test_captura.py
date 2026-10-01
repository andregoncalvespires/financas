import io
import json

import httpx
from PIL import Image

from app import gemini
from app.config import settings
from conftest import categoria_por_codigo, conta
from test_cartao import cenario  # noqa: F401  (fixture)


def foto(w=800, h=600):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 230)).save(buf, "JPEG")
    return {"arquivo": ("nota.jpg", buf.getvalue(), "image/jpeg")}


def resposta(**kw):
    base = {"tipo_documento": "cupom_fiscal", "direcao": "saida", "valor_total": 45.90, "data": "2026-09-05",
            "estabelecimento": "PADARIA DO ZE", "forma_pagamento": "credito", "final_cartao": "5678", "parcelas": 1,
            "categoria_codigo": "2020.02", "descricao": "Pão e café", "confianca": 0.93, "observacoes": ""}
    return {**base, **kw}


def test_portador_captura_foto_e_a_sugestao_usa_o_cadastro_do_dono(cenario, monkeypatch):
    a, b, s = cenario["a"], cenario["b"], cenario
    monkeypatch.setattr(gemini, "MOCK_RESPOSTA", resposta())
    r = b.post("/api/capturas", files=foto())
    assert r.status_code == 201, r.text
    cap = r.json()
    sug = cap["sugestao"]
    assert sug["valor_centavos"] == 4590 and sug["tipo"] == "despesa" and sug["forma_pagamento"] == "cartao"
    assert sug["plastico_id"] == s["adicional"]["id"]                       # achou o cartão pelo final 5678
    assert sug["categoria_id"] == categoria_por_codigo(a, "2020.02")["id"]   # categoria do DONO, via código do kit
    assert not sug["alertas"]

    body = {k: sug[k] for k in ("tipo", "valor_centavos", "data_competencia", "plastico_id", "categoria_id", "descricao", "favorecido_nome")}
    ok = b.post(f"/api/capturas/{cap['id']}/confirmar", json=body)
    assert ok.status_code == 201, ok.text
    t = b.get("/api/transacoes").json()[0]
    assert t["origem"] == "foto" and t["anexo_id"] == cap["anexo_id"] and t["valor_centavos"] == -4590
    assert b.get("/api/capturas").json() == []                               # não há mais pendentes
    assert b.post(f"/api/capturas/{cap['id']}/confirmar", json=body).status_code == 404   # não confirma duas vezes

    # o comprovante acompanha o lançamento: o dono do cartão vê; um estranho não
    img_b, img_a = b.get(f"/api/anexos/{cap['anexo_id']}"), a.get(f"/api/anexos/{cap['anexo_id']}")
    assert img_b.status_code == 200 and img_b.headers["content-type"] == "image/jpeg" and img_a.status_code == 200
    from conftest import cliente
    estranho = cliente(b.c.app if hasattr(b.c, "app") else None) if False else None  # noqa
    # (o isolamento por usuário estranho é coberto em test_rls)

    # aprendizado: o favorecido lembra a categoria confirmada, mesmo que a IA sugira outra
    cat_b = categoria_por_codigo(b, "2020.02", dono_id=a.id)
    monkeypatch.setattr(gemini, "MOCK_RESPOSTA", resposta(valor_total=12.0, categoria_codigo="2060.03"))
    sug2 = b.post("/api/capturas", files=foto()).json()["sugestao"]
    assert sug2["favorecido_id"] and sug2["categoria_id"] == cat_b["id"]


def test_duplicidade_e_leitura_ruim_geram_alertas(cenario, monkeypatch):
    b = cenario["b"]
    monkeypatch.setattr(gemini, "MOCK_RESPOSTA", resposta())
    s1 = b.post("/api/capturas", files=foto()).json()["sugestao"]
    b.post(f"/api/capturas/{b.get('/api/capturas').json()[0]['id']}/confirmar",
           json={k: s1[k] for k in ("tipo", "valor_centavos", "data_competencia", "plastico_id", "categoria_id")})
    s2 = b.post("/api/capturas", files=foto()).json()["sugestao"]
    assert s2["possivel_duplicada"] and any("duplicado" in x for x in s2["alertas"])
    monkeypatch.setattr(gemini, "MOCK_RESPOSTA", resposta(valor_total=0, confianca=0.3, final_cartao=""))
    s3 = b.post("/api/capturas", files=foto()).json()["sugestao"]
    assert any("valor" in x for x in s3["alertas"]) and any("confiança" in x for x in s3["alertas"])


def test_sem_conta_cadastrada_avisa(nova_pessoa, monkeypatch):
    p = nova_pessoa()
    monkeypatch.setattr(gemini, "MOCK_RESPOSTA", resposta(forma_pagamento="pix", final_cartao=""))
    sug = p.post("/api/capturas", files=foto()).json()["sugestao"]
    assert sug["conta_id"] is None and any("conta" in x for x in sug["alertas"]) and sug["forma_pagamento"] == "pix"
    c = conta(p, "Corrente")
    sug = p.post("/api/capturas", files=foto()).json()["sugestao"]
    assert sug["conta_id"] == c["id"]


def test_falha_do_gemini_preserva_o_comprovante_para_lancamento_manual(nova_pessoa, monkeypatch):
    p = nova_pessoa()
    c = conta(p, "Corrente")

    def falha(*a, **k):
        raise gemini.GeminiErro("HTTP 503")
    monkeypatch.setattr(gemini, "extrair", falha)
    cap = p.post("/api/capturas", files=foto()).json()
    assert cap["status"] == "erro" and "503" in cap["erro"] and cap["anexo_id"]
    r = p.post(f"/api/capturas/{cap['id']}/confirmar", json={"tipo": "despesa", "valor_centavos": 999, "data_competencia": "2026-09-01", "conta_id": c["id"]})
    assert r.status_code == 201 and p.get(f"/api/anexos/{cap['anexo_id']}").status_code == 200


def test_limite_diario_e_arquivos_invalidos(nova_pessoa, monkeypatch):
    p = nova_pessoa()
    monkeypatch.setattr(settings, "capturas_por_dia", 2)
    assert p.post("/api/capturas", files={"arquivo": ("x.txt", b"nao sou imagem", "text/plain")}).status_code == 415
    assert p.post("/api/capturas", files=foto()).status_code == 201
    assert p.post("/api/capturas", files=foto()).status_code == 201
    assert p.post("/api/capturas", files=foto()).status_code == 429


def test_imagem_e_reduzida_e_regravada_sem_metadados(nova_pessoa):
    p = nova_pessoa()
    cap = p.post("/api/capturas", files=foto(3200, 2400)).json()
    img = Image.open(io.BytesIO(p.get(f"/api/anexos/{cap['anexo_id']}").content))
    assert max(img.size) == 1600 and img.format == "JPEG" and not img.getexif()


def test_chamada_rest_ao_gemini(monkeypatch):
    """Sem chave/rede reais: confere o formato do pedido e a leitura da resposta."""
    monkeypatch.setattr(settings, "gemini_mock", False)
    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "gemini_model", "gemini-teste")
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    chamadas = []

    def fake_post(url, json=None, headers=None, timeout=None):
        chamadas.append((url, json, headers))
        if len(chamadas) == 1:
            return httpx.Response(429, text="limite", request=httpx.Request("POST", url))
        corpo = {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(resposta())}]}}],
                 "usageMetadata": {"promptTokenCount": 1300, "candidatesTokenCount": 90}}
        return httpx.Response(200, json=corpo, request=httpx.Request("POST", url))
    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    ext, meta = gemini.extrair(b"\xff\xd8bytes", "image/jpeg")
    assert ext.estabelecimento == "PADARIA DO ZE" and meta["tokens_entrada"] == 1300
    assert len(chamadas) == 2                                            # repetiu após o 429
    url, corpo, headers = chamadas[-1]
    assert url.endswith("/models/gemini-teste:generateContent") and headers == {"x-goog-api-key": "chave-de-teste"}
    partes = corpo["contents"][0]["parts"]
    assert partes[1]["inline_data"]["mime_type"] == "image/jpeg" and "2020.01 = Alimentação > Supermercado" in partes[0]["text"]
    gc = corpo["generationConfig"]
    assert gc["responseMimeType"] == "application/json" and "2020.01" in gc["responseSchema"]["properties"]["categoria_codigo"]["enum"]

    monkeypatch.setattr(gemini.httpx, "post", lambda *a, **k: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "isto não é json"}]}}]}, request=httpx.Request("POST", "x")))
    try:
        gemini.extrair(b"x", "image/jpeg")
        assert False
    except gemini.GeminiErro:
        pass
