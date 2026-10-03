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


def extrair(dados: bytes, mime: str, chave: str | None = None) -> tuple[Extracao, dict]:
    """Retorna (extração validada, metadados de uso)."""
    if settings.gemini_mock:
        return Extracao(**_mock()), {"modelo": "mock"}
    chave = chave or settings.gemini_api_key
    if not chave:
        raise GeminiErro("leitura por IA não configurada")
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
            r = httpx.post(url, json=corpo, headers={"x-goog-api-key": chave}, timeout=60)
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


# ---------- fatura de cartão (PDF com várias páginas) ----------
SCHEMA_FATURA = {
    "type": "OBJECT",
    "properties": {
        "emissor": {"type": "STRING"},
        "vencimento": {"type": "STRING"},
        "fechamento": {"type": "STRING"},
        "total_fatura": {"type": "NUMBER"},
        "linhas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "data": {"type": "STRING"},
            "descricao": {"type": "STRING"},
            "valor": {"type": "NUMBER"},
            "valor_usd": {"type": "NUMBER"},
            "parcela_atual": {"type": "INTEGER"},
            "parcelas_total": {"type": "INTEGER"},
            "final_cartao": {"type": "STRING"},
            "tipo": {"type": "STRING", "enum": ["compra", "iof_exterior", "estorno_credito", "pagamento", "encargo", "outro"]},
            "categoria_codigo": {"type": "STRING"},
        }, "required": ["data", "descricao", "valor", "parcela_atual", "parcelas_total", "final_cartao", "tipo"]}},
    },
    "required": ["vencimento", "fechamento", "total_fatura", "linhas"],
}

PROMPT_FATURA = """Você lê a FATURA de um cartão de crédito brasileiro (PDF, possivelmente com várias páginas) e devolve os dados estruturados.

Cabeçalho:
- vencimento e fechamento: AAAA-MM-DD. fechamento = último dia do período de compras desta fatura (ou a data de fechamento informada).
- total_fatura: valor total a pagar desta fatura, em reais, com ponto decimal.
- emissor: nome do banco/emissor.

linhas: UMA entrada para cada lançamento da seção de detalhamento (despesas, parcelamentos, créditos), na ordem em que aparecem, de TODOS os cartões (titular e adicionais). Não leia o resumo, o histórico de faturas, nem opções de pagamento como se fossem lançamentos.
- data: AAAA-MM-DD. A fatura mostra só dia/mês: use o ano que faz a data ser anterior ou igual ao fechamento (compras de dezembro numa fatura de janeiro são do ano anterior).
- descricao: o texto do estabelecimento exatamente como impresso (ex.: "SUPERMERCADOS BH"), sem a data e sem o valor.
- valor: valor em reais, positivo para compras; NEGATIVO para créditos, estornos e pagamentos recebidos.
- valor_usd: valor em dólar quando houver, senão 0.
- parcela_atual / parcelas_total: SOMENTE quando existir um texto "NN/NN" (ex.: "03/10") na coluna Parcela daquela linha. Ícones da coluna "Compra" (ondas de pagamento por aproximação, "@" de compra online, etc.) NÃO são parcelas. Coluna Parcela vazia => 1 e 1. Em caso de dúvida, use 1 e 1.
- final_cartao: 4 últimos dígitos do cartão da seção em que o lançamento aparece (o cabeçalho de cada seção traz o número mascarado). Se não houver, string vazia.
- tipo: "compra" para compras e parcelas; "iof_exterior" para a linha de IOF de compra no exterior (que fica logo abaixo da compra em moeda estrangeira; NÃO some o valor na compra, mantenha como linha separada logo depois dela); "estorno_credito" para estornos/créditos; "pagamento" para pagamentos da fatura anterior; "encargo" para juros, multa, anuidade e tarifas; "outro" para o resto.
- categoria_codigo: para compras, escolha UM código da lista de categorias abaixo, o que melhor descreve o estabelecimento (ex.: supermercado, posto de combustível, farmácia, restaurante, aplicativo de transporte, assinatura de streaming). Para o que não for compra, ou se não souber, deixe string vazia.
- Linhas de cotação do dólar ("COTAÇÃO DOLAR...") não são lançamentos: ignore-as.
- Não invente linhas. Não repita linhas de subtotal ("VALOR TOTAL").

Categorias (código = Grupo > Nome):
{categorias}
"""

MOCK_FATURA: dict | None = None   # os testes sobrescrevem


def extrair_fatura(dados: bytes, chave: str | None = None) -> tuple[dict, dict]:
    """Lê uma fatura em PDF. Retorna (dados brutos validados, metadados de uso)."""
    if settings.gemini_mock:
        return dict(MOCK_FATURA or {"vencimento": date.today().isoformat(), "fechamento": date.today().isoformat(), "total_fatura": 0, "linhas": []}), {"modelo": "mock"}
    chave = chave or settings.gemini_api_key
    if not chave:
        raise GeminiErro("leitura por IA não configurada")
    corpo = {
        "contents": [{"parts": [
            {"text": PROMPT_FATURA.replace("{categorias}", catalogo_para_prompt())},
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(dados).decode()}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA_FATURA, "temperature": 0, "maxOutputTokens": 32768},
    }
    url = ENDPOINT.format(modelo=settings.gemini_model)
    ultimo = ""
    for tentativa in range(3):
        try:
            r = httpx.post(url, json=corpo, headers={"x-goog-api-key": chave}, timeout=180)
        except httpx.HTTPError as e:
            ultimo = f"falha de rede: {e.__class__.__name__}"
        else:
            if r.status_code == 200:
                resp = r.json()
                try:
                    out = json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
                except (KeyError, IndexError, ValueError):
                    raise GeminiErro("resposta inesperada do modelo (a fatura pode ser grande demais ou ilegível)")
                uso = resp.get("usageMetadata", {})
                return out, {"modelo": settings.gemini_model, "tokens_entrada": uso.get("promptTokenCount"), "tokens_saida": uso.get("candidatesTokenCount")}
            ultimo = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code not in (429, 500, 503):
                break
        time.sleep(2 * (tentativa + 1))
    raise GeminiErro(ultimo)
