"""Importação de fatura de cartão em PDF: lê com IA, compara com o que já foi lançado e deixa a pessoa conferir antes de gravar."""
import io
import json
import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from uuid import uuid4

import pikepdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import gemini
from ..config import settings
from ..db import sessao
from ..deps import Usuario, get_db, usuario_atual
from ..schemas import ImportarFaturaIn
from ..servicos import add_months, aprender_categoria, dono_do_alvo, norm, resolver_favorecido_categoria

router = APIRouter(prefix="/api")
MAX_BYTES = 12 * 1024 * 1024
FORA_DA_CARGA = {"pagamento": "pagamento da fatura anterior", "encargo": "encargo (juros, multa ou tarifa)", "outro": "não é compra"}


def abrir_pdf(bruto: bytes, senha: str) -> bytes:
    """Devolve o PDF sem proteção, só em memória. A senha nunca é guardada."""
    if bruto[:5] != b"%PDF-":
        raise HTTPException(415, "envie o PDF da fatura")
    try:
        with pikepdf.open(io.BytesIO(bruto), password=senha or "") as pdf:
            saida = io.BytesIO()
            pdf.save(saida)
            return saida.getvalue()
    except pikepdf.PasswordError:
        raise HTTPException(422, "senha do PDF incorreta ou não informada")
    except pikepdf.PdfError:
        raise HTTPException(422, "não consegui abrir este PDF")


def _data(s: str, fallback: date | None = None) -> date | None:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return fallback


def limpar_nome(bruto: str) -> str:
    """'DL *UBERRIDES' -> 'Uberrides'; 'MP*ALIEXPRESS' -> 'Aliexpress'. O texto original continua na descrição."""
    s = re.sub(r"^\s*(DL|MP|ZP|PG|IZ|PP|EC|PAG|PICPAY)\s*\*\s*", "", (bruto or "").strip(), flags=re.I)
    s = re.sub(r"\s*\*\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s.title() if s.isupper() else s


def _parecidos(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def normalizar_linhas(bruto: dict, vencimento: date, fechamento: date) -> list[dict]:
    """Valida o que a IA devolveu, corrige o ano, junta o IOF no exterior à compra e separa o que não é compra."""
    saida: list[dict] = []
    for r in bruto.get("linhas") or []:
        d = _data(r.get("data"))
        if d and d > fechamento + timedelta(days=1):
            d = d.replace(year=d.year - 1) if not (d.month == 2 and d.day == 29) else d.replace(year=d.year - 1, day=28)
        try:
            valor = round(float(r.get("valor") or 0) * 100)
        except (TypeError, ValueError):
            valor = 0
        tipo = r.get("tipo") or "compra"
        if not d or not valor:
            continue
        if tipo == "iof_exterior" and saida and saida[-1]["tipo"] == "compra":
            saida[-1]["valor_centavos"] += abs(valor)
            saida[-1]["iof_centavos"] = saida[-1].get("iof_centavos", 0) + abs(valor)
            continue
        saida.append({
            "data": d, "descricao": (r.get("descricao") or "").strip()[:200], "tipo": "estorno_credito" if (valor < 0 and tipo == "compra") else tipo,
            "valor_centavos": abs(valor), "eh_credito": valor < 0 or tipo == "estorno_credito",
            "valor_usd": float(r.get("valor_usd") or 0), "final_cartao": re.sub(r"\D", "", r.get("final_cartao") or "")[-4:],
            "parcela_atual": max(1, int(r.get("parcela_atual") or 1)), "parcelas_total": max(1, int(r.get("parcelas_total") or 1)),
        })
    return saida


def _casar(linhas: list[dict], candidatos: list[dict]) -> None:
    """Liga cada linha da fatura a um lançamento do app (mesmo cartão, data próxima, nome parecido). Cada lançamento casa uma vez."""
    usados: set = set()
    def sinal(c): return c["valor_centavos"] > 0
    def melhor(l, exigir_valor):
        melhor_c, melhor_s = None, 0.0
        for c in candidatos:
            if c["id"] in usados or sinal(c) != l["eh_credito"]:
                continue
            dias = abs((c["data_ref"] - l["data"]).days)
            if dias > 4:
                continue
            igual = abs(c["valor_centavos"]) == l["valor_centavos"]
            if exigir_valor and not igual:
                continue
            sim = _parecidos(c["descricao"] or c["favorecido_nome"] or "", l["descricao"])
            sim2 = _parecidos(c["favorecido_nome"] or "", limpar_nome(l["descricao"]))
            sim = max(sim, sim2)
            prox = abs(abs(c["valor_centavos"]) - l["valor_centavos"]) / max(l["valor_centavos"], 1)
            if not exigir_valor and (sim < 0.6 or prox > 0.35):
                continue
            pontos = (2 if igual else 0) + sim + (1 - dias / 5) * 0.5
            if pontos > melhor_s:
                melhor_c, melhor_s = c, pontos
        return melhor_c
    for exigir in (True, False):     # primeiro os casamentos exatos; depois os de valor diferente
        for l in linhas:
            if l.get("casamento") or l["tipo"] not in ("compra", "estorno_credito"):
                continue
            c = melhor(l, exigir)
            if c:
                usados.add(c["id"])
                l["casamento"] = {"transacao_id": c["id"], "valor_centavos": abs(c["valor_centavos"]), "data": c["data_ref"], "descricao": c["descricao"] or c["favorecido_nome"],
                                  "diferenca_centavos": l["valor_centavos"] - abs(c["valor_centavos"])}
    for c in candidatos:
        c["casou"] = c["id"] in usados


@router.post("/faturas/importar/ler")
def ler(arquivo: UploadFile = File(...), cartao_id: str = Form(...), senha: str = Form(""), usuario: Usuario = Depends(usuario_atual)):
    bruto = arquivo.file.read(MAX_BYTES + 1)
    if len(bruto) > MAX_BYTES:
        raise HTTPException(413, "arquivo maior que 12 MB")
    pdf = abrir_pdf(bruto, senha)
    with sessao(usuario.id) as cur:
        if not cur.execute("SELECT dono_cartao(%s) AS ok", (cartao_id,)).fetchone()["ok"]:
            raise HTTPException(403, "só o dono da conta de cartão importa faturas")
        n = cur.execute("SELECT count(*) AS n FROM captura WHERE criado_por = %s AND criado_em > now() - interval '24 hours'", (usuario.id,)).fetchone()["n"]
        if n >= settings.capturas_por_dia:
            raise HTTPException(429, f"limite de {settings.capturas_por_dia} leituras por dia atingido")
        cap = cur.execute("INSERT INTO captura(criado_por, status) VALUES (%s, 'descartada') RETURNING id", (usuario.id,)).fetchone()   # só para contar o uso diário
    try:
        bruto_ia, meta = gemini.extrair_fatura(pdf)
        erro = None
    except gemini.GeminiErro as e:
        bruto_ia, meta, erro = None, {}, str(e)
    if erro:
        with sessao(usuario.id) as cur:
            cur.execute("UPDATE captura SET status = 'erro', erro = %s WHERE id = %s", (erro[:500], cap["id"]))
        raise HTTPException(502, "não consegui ler a fatura agora: " + erro[:200])
    venc = _data(bruto_ia.get("vencimento"))
    fech = _data(bruto_ia.get("fechamento"), venc)
    if not venc or not fech:
        raise HTTPException(422, "não encontrei o vencimento: este PDF parece não ser uma fatura de cartão")
    linhas = normalizar_linhas(bruto_ia, venc, fech)
    with sessao(usuario.id) as cur:
        cur.execute("UPDATE captura SET resultado = %s::jsonb, modelo = %s WHERE id = %s", (json.dumps(bruto_ia), meta.get("modelo"), cap["id"]))
        return montar_previa(cur, cartao_id, venc, fech, bruto_ia, linhas)


def montar_previa(cur, cartao_id, venc: date, fech: date, bruto_ia: dict, linhas: list[dict]) -> dict:
    k = cur.execute("SELECT id, nome, dono_id, dia_fechamento, dia_vencimento FROM cartao WHERE id = %s", (cartao_id,)).fetchone()
    pls = cur.execute("SELECT id, final, rotulo, principal FROM plastico WHERE cartao_id = %s AND ativo ORDER BY principal DESC", (cartao_id,)).fetchall()
    if not pls:
        raise HTTPException(422, "esta conta de cartão não tem cartão ativo cadastrado")
    por_final = {p["final"]: p for p in pls if p["final"]}
    fat = cur.execute("SELECT id, status FROM fatura WHERE cartao_id = %s AND data_vencimento = %s", (cartao_id, venc)).fetchone()
    alertas: list[str] = []
    if fat and fat["status"] == "paga":
        alertas.append("esta fatura já está marcada como paga no app")
    if not fat and (k["dia_fechamento"] != fech.day or k["dia_vencimento"] != venc.day):
        alertas.append(f"o cartão está configurado com fechamento dia {k['dia_fechamento']} e vencimento dia {k['dia_vencimento']}, mas a fatura traz fechamento {fech:%d/%m} e vencimento {venc:%d/%m}: ajuste o cartão antes de importar")
    lo, hi = add_months(fech, -1) - timedelta(days=6), fech + timedelta(days=6)
    cand = cur.execute("""
        SELECT t.id, t.valor_centavos, COALESCE(t.data_compra, t.data_competencia) AS data_ref, t.descricao, f.nome AS favorecido_nome, t.fatura_id
        FROM transacao t JOIN plastico p ON p.id = t.plastico_id LEFT JOIN favorecido f ON f.id = t.favorecido_id
        WHERE p.cartao_id = %s AND t.tipo IN ('despesa','receita')
          AND (t.fatura_id = %s OR (COALESCE(t.data_compra, t.data_competencia) BETWEEN %s AND %s AND t.numero_parcela IS NULL))""",
        (cartao_id, fat["id"] if fat else None, lo, hi)).fetchall()
    _casar(linhas, cand)
    # sugestão de favorecido e categoria (histórico da mesma descrição, depois o favorecido cadastrado)
    for i, l in enumerate(linhas):
        l["i"] = i
        pl = por_final.get(l["final_cartao"]) or pls[0]
        l["plastico_id"] = pl["id"]
        l["plastico_rotulo"] = f"·· {pl['final']}" if pl["final"] else pl["rotulo"]
        if l["final_cartao"] and l["final_cartao"] not in por_final:
            l["alerta"] = f"nenhum cartão cadastrado termina em {l['final_cartao']}: usei o principal"
        nome = limpar_nome(l["descricao"])
        n = norm(nome)
        fav = cur.execute("SELECT id, nome, categoria_padrao_id FROM favorecido WHERE dono_id = %s AND (nome_norm = %s OR (length(nome_norm) >= 5 AND %s LIKE nome_norm || '%%')) ORDER BY length(nome_norm) DESC LIMIT 1",
                          (k["dono_id"], n, n)).fetchone() if n else None
        hist = cur.execute("""SELECT t.categoria_id FROM transacao t JOIN plastico p ON p.id = t.plastico_id
                              WHERE p.cartao_id = %s AND t.descricao = %s AND t.categoria_id IS NOT NULL ORDER BY t.criado_em DESC LIMIT 1""", (cartao_id, l["descricao"])).fetchone()
        l["favorecido_nome"] = fav["nome"] if fav else nome
        l["favorecido_id"] = fav["id"] if fav else None
        l["categoria_id"] = (hist["categoria_id"] if hist else None) or (fav["categoria_padrao_id"] if fav else None)
        if l["tipo"] in FORA_DA_CARGA:
            l["acao_sugerida"] = "ignorar"
            l["motivo"] = FORA_DA_CARGA[l["tipo"]]
        elif l.get("casamento"):
            l["acao_sugerida"] = "atualizar" if l["casamento"]["diferenca_centavos"] or l["casamento"]["data"] != l["data"] else "conferir"
        else:
            l["acao_sugerida"] = "criar"
    soma = sum((-1 if l["eh_credito"] else 1) * l["valor_centavos"] for l in linhas if l["tipo"] in ("compra", "estorno_credito"))
    total = round(float(bruto_ia.get("total_fatura") or 0) * 100)
    return {
        "cartao": {"id": k["id"], "nome": k["nome"]},
        "fatura": {"vencimento": venc, "fechamento": fech, "id": fat["id"] if fat else None, "emissor": bruto_ia.get("emissor") or "",
                   "total_centavos": total, "soma_compras_centavos": soma, "diferenca_centavos": total - soma},
        "linhas": linhas, "alertas": alertas,
        "no_app_sem_par": [{"id": c["id"], "data": c["data_ref"], "descricao": c["descricao"] or c["favorecido_nome"], "valor_centavos": abs(c["valor_centavos"]), "eh_credito": c["valor_centavos"] > 0}
                           for c in cand if not c["casou"] and fat and c["fatura_id"] == fat["id"]],
    }


@router.post("/faturas/importar/aplicar")
def aplicar(body: ImportarFaturaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    if not cur.execute("SELECT dono_cartao(%s) AS ok", (body.cartao_id,)).fetchone()["ok"]:
        raise HTTPException(403, "só o dono da conta de cartão importa faturas")
    cartao = str(body.cartao_id)
    pls = {str(p["id"]): p for p in cur.execute("SELECT id, principal FROM plastico WHERE cartao_id = %s", (cartao,)).fetchall()}
    principal = next((i for i, p in pls.items() if p["principal"]), next(iter(pls), None))
    if not principal:
        raise HTTPException(422, "esta conta de cartão não tem cartão cadastrado")
    fat = cur.execute("SELECT id, status, data_vencimento FROM fatura WHERE cartao_id = %s AND data_vencimento = %s", (cartao, body.vencimento)).fetchone()
    if not fat and any(l.acao == "criar" for l in body.linhas):
        # a fatura ainda não existe no app: cria pelo fechamento mais recente e confere se bate com o vencimento do PDF
        ref = min((l.data for l in body.linhas if l.acao == "criar"), default=body.vencimento)
        f = cur.execute("SELECT * FROM fatura_para_compra(%s, %s)", (principal, ref)).fetchone()
        fat = cur.execute("SELECT id, status, data_vencimento FROM fatura WHERE id = %s", (f["fatura_id"],)).fetchone()
        if fat["data_vencimento"] != body.vencimento:
            raise HTTPException(422, f"o vencimento da fatura ({body.vencimento:%d/%m/%Y}) não bate com o do app ({fat['data_vencimento']:%d/%m/%Y}): confira o fechamento e o vencimento do cartão")
    if fat and fat["status"] == "paga":
        raise HTTPException(409, "esta fatura já está paga no app; reabra-a antes de importar")
    criadas = atualizadas = 0
    for l in body.linhas:
        if l.acao in ("conferir", "ignorar"):
            continue
        if l.acao == "atualizar":
            t = cur.execute("""SELECT t.id, t.valor_centavos, t.numero_parcela FROM transacao t JOIN plastico p ON p.id = t.plastico_id
                               WHERE t.id = %s AND p.cartao_id = %s AND t.tipo IN ('despesa','receita')""", (l.transacao_id, cartao)).fetchone()
            if not t:
                raise HTTPException(404, "lançamento a atualizar não encontrado neste cartão")
            novo = l.valor_centavos * (1 if t["valor_centavos"] > 0 else -1)
            cur.execute("UPDATE transacao SET valor_centavos = %s, data_compra = %s, data_competencia = CASE WHEN numero_parcela IS NULL THEN %s ELSE data_competencia END WHERE id = %s",
                        (novo, l.data, l.data, t["id"]))
            atualizadas += 1
            continue
        plastico = str(l.plastico_id) if l.plastico_id else principal
        if plastico not in pls:
            raise HTTPException(422, "cartão da linha não pertence a esta conta de cartão")
        dono = dono_do_alvo(cur, None, plastico)
        fav, cat = resolver_favorecido_categoria(cur, dono, l.favorecido_id, l.favorecido_nome, l.categoria_id)
        n, k = l.parcelas_total, min(l.parcela_atual, l.parcelas_total)
        comp = add_months(l.data, k - 1) if n > 1 else l.data
        cur.execute(
            """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, data_compra, plastico_id, fatura_id,
                 forma_pagamento, categoria_id, favorecido_id, descricao, parcelamento_id, numero_parcela, total_parcelas, origem)
               VALUES (%s,%s,'confirmado',%s,%s,%s,%s,%s,%s,'cartao',%s,%s,%s,%s,%s,%s,'fatura')""",
            (usuario.id, "receita" if l.eh_credito else "despesa", l.valor_centavos * (1 if l.eh_credito else -1), comp, fat["data_vencimento"], l.data,
             plastico, fat["id"], cat, fav, l.descricao, uuid4() if n > 1 else None, k if n > 1 else None, n if n > 1 else None))
        aprender_categoria(cur, fav, cat)
        criadas += 1
    return {"criadas": criadas, "atualizadas": atualizadas, "fatura_id": fat["id"] if fat else None}
