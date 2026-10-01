"""Extração de dados de comprovantes com a API do Gemini (REST). A chave fica só no servidor."""
import base64
import json
import time
from datetime import date

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings
from .kit import catalogo_para_prompt, linhas

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
CODIGOS = [c for c, *_ in linhas()]

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "tipo_documento": {"type": "STRING", "enum": ["cupom_fiscal", "comprovante_pix", "comprovante_cartao", "boleto", "fatura", "extrato", "notificacao", "outro"]},
        "direcao": {"type": "STRING", "enum": ["saida", "entrada"]},
        "valor_total": {"type": "NUMBER"},
        "data": {"type": "STRING"},
        "estabelecimento": {"type": "STRING"},
        "forma_pagamento": {"type": "STRING", "enum": ["credito", "debito", "pix", "dinheiro", "boleto", "transferencia", "desconhecida"]},
        "final_cartao": {"type": "STRING"},
        "parcelas": {"type": "INTEGER"},
        "categoria_codigo": {"type": "STRING", "enum": CODIGOS},
        "descricao": {"type": "STRING"},
        "confianca": {"type": "NUMBER"},
        "observacoes": {"type": "STRING"},
    },
    "required": ["tipo_documento", "direcao", "valor_total", "data", "estabelecimento", "forma_pagamento", "final_cartao",
                 "parcelas", "categoria_codigo", "descricao", "confianca"],
    "propertyOrdering": ["tipo_documento", "direcao", "valor_total", "data", "estabelecimento", "forma_pagamento", "final_cartao",
                         "parcelas", "categoria_codigo", "descricao", "confianca", "observacoes"],
}

PROMPT = """Você extrai dados de comprovantes financeiros brasileiros (cupom fiscal, nota, comprovante de Pix, recibo de cartão, \
boleto, notificação de banco) a partir da imagem ou PDF anexado.

Regras:
- valor_total: valor final pago, em reais, com ponto decimal (ex.: 87.30). Se houver vários, use o TOTAL. Se não achar, 0.
- data: formato AAAA-MM-DD. Se só houver dia e mês, use o ano {ano}. Se não achar, string vazia.
- direcao: "saida" para compras e pagamentos; "entrada" para valores recebidos.
- estabelecimento: nome comercial curto, sem CNPJ, endereço ou razão social longa.
- forma_pagamento: credito, debito, pix, dinheiro, boleto, transferencia ou desconhecida.
- final_cartao: os 4 últimos dígitos do cartão se aparecerem (ex.: "**** 1234" → "1234"); senão string vazia. Nunca informe número completo.
- parcelas: número de parcelas se for crédito parcelado; senão 1.
- categoria_codigo: escolha exatamente UM código da lista abaixo, o que melhor descreve a despesa (ou receita).
- descricao: até 60 caracteres, o que foi comprado/pago.
- confianca: de 0 a 1, quão seguro você está dos dados.
- Não invente dados. Se a imagem não for um documento financeiro, use tipo_documento "outro" e valor_total 0.

Categorias (código = Grupo > Nome):
{categorias}
"""


class Extracao(BaseModel):
    tipo_documento: str = "outro"
    direcao: str = "saida"
    valor_total: float = Field(default=0, ge=0)
    data: str = ""
    estabelecimento: str = ""
    forma_pagamento: str = "desconhecida"
    final_cartao: str = ""
    parcelas: int = Field(default=1, ge=1, le=60)
    categoria_codigo: str = ""
    descricao: str = ""
    confianca: float = 0
    observacoes: str = ""


class GeminiErro(Exception):
    pass


MOCK_RESPOSTA: dict | None = None   # os testes sobrescrevem


def _mock() -> dict:
    return MOCK_RESPOSTA or {
        "tipo_documento": "cupom_fiscal", "direcao": "saida", "valor_total": 87.30, "data": date.today().isoformat(),
        "estabelecimento": "SUPERMERCADO EXEMPLO", "forma_pagamento": "credito", "final_cartao": "",
        "parcelas": 1, "categoria_codigo": "2020.01", "descricao": "Compras do mês", "confianca": 0.9, "observacoes": "",
    }


def extrair(dados: bytes, mime: str) -> tuple[Extracao, dict]:
    """Retorna (extração validada, metadados de uso)."""
    if settings.gemini_mock:
        return Extracao(**_mock()), {"modelo": "mock"}
    if not settings.gemini_api_key:
        raise GeminiErro("GEMINI_API_KEY não configurada no servidor")
    corpo = {
        "contents": [{"parts": [
            {"text": PROMPT.format(ano=date.today().year, categorias=catalogo_para_prompt())},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(dados).decode()}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.1},
    }
    url = ENDPOINT.format(modelo=settings.gemini_model)
    ultimo = ""
    for tentativa in range(3):
        try:
            r = httpx.post(url, json=corpo, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=60)
        except httpx.HTTPError as e:
            ultimo = f"falha de rede: {e.__class__.__name__}"
        else:
            if r.status_code == 200:
                return _interpretar(r.json())
            ultimo = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code not in (429, 500, 503):
                break
        time.sleep(1.5 * (tentativa + 1))
    raise GeminiErro(ultimo)


def _interpretar(resp: dict) -> tuple[Extracao, dict]:
    try:
        texto = resp["candidates"][0]["content"]["parts"][0]["text"]
        ext = Extracao(**json.loads(texto))
    except (KeyError, IndexError, ValueError, ValidationError) as e:
        raise GeminiErro(f"resposta inesperada do modelo: {e.__class__.__name__}")
    uso = resp.get("usageMetadata", {})
    return ext, {"modelo": settings.gemini_model, "tokens_entrada": uso.get("promptTokenCount"), "tokens_saida": uso.get("candidatesTokenCount")}
