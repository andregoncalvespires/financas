"""Contas de investimento: cadastro (subtipo, rendimento, aniversário, vencimento), premissas, rendimento previsto,
valor informado à mão (renda variável) e aviso de vencimento. Tudo é estimativa e não substitui o extrato."""
import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from .. import mailer
from ..db import sessao
from ..deps import Usuario, get_db, usuario_atual
from ..investimentos_calc import (SUBTIPOS, aliquota_para, mes_mais, premissas_com_padrao, projetar)
from ..schemas import AtualizarValorIn, InvestimentoIn, PremissasIn

log = logging.getLogger("uvicorn.error.invest")
router = APIRouter(prefix="/api")
HORIZONTE = 6          # meses de rendimento previsto à frente (mês atual + 5), como nas recorrências

SALDO = """(c.saldo_inicial_centavos + COALESCE((SELECT SUM(t.valor_centavos) FROM transacao t
            WHERE t.conta_id = c.id AND t.estado IN ('confirmado','conciliado') AND t.data_caixa >= c.data_saldo_inicial), 0))::bigint"""


@router.get("/subtipos-investimento")
def subtipos():
    return [{"chave": k, "rotulo": v[0], "indexador": v[1], "isento_ir": v[2], "manual": v[3]} for k, v in SUBTIPOS.items()]


def _premissas(cur, uid) -> dict:
    cfg = cur.execute("SELECT config FROM usuario WHERE id = %s", (uid,)).fetchone()
    return premissas_com_padrao(cfg["config"] if cfg else None)


@router.get("/premissas")
def ler_premissas(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    cfg = cur.execute("SELECT config FROM usuario WHERE id = %s", (usuario.id,)).fetchone()["config"]
    return {**premissas_com_padrao(cfg), "personalizadas": bool((cfg or {}).get("premissas"))}


@router.put("/premissas")
def salvar_premissas(body: PremissasIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    cur.execute("UPDATE usuario SET config = config || %s::jsonb WHERE id = %s", (json.dumps({"premissas": body.model_dump()}), usuario.id))
    recalcular(cur, usuario)                     # os rendimentos previstos passam a usar as premissas novas
    return {**body.model_dump(), "personalizadas": True}


def _inv_dict(r: dict) -> dict:
    return {k: r[k] for k in ("subtipo", "indexador", "taxa", "data_aplicacao", "dia_aniversario", "data_vencimento", "isento_ir")}


@router.get("/investimentos")
def listar(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    hoje = date.today()
    prem = _premissas(cur, usuario.id)
    rs = cur.execute(
        f"""SELECT c.id, c.nome, c.dono_id, papel_conta(c.id) AS papel, {SALDO} AS saldo_atual,
                   i.subtipo, i.indexador, i.taxa, i.data_aplicacao, i.dia_aniversario, i.data_vencimento, i.isento_ir, i.alerta_dias,
                   (i.conta_id IS NOT NULL) AS configurado,
                   (SELECT t.valor_centavos FROM transacao t WHERE t.conta_id = c.id AND t.origem = 'rendimento' AND t.estado = 'previsto'
                     ORDER BY t.data_competencia LIMIT 1) AS rendimento_proximo,
                   (SELECT t.data_competencia FROM transacao t WHERE t.conta_id = c.id AND t.origem = 'rendimento' AND t.estado = 'previsto'
                     ORDER BY t.data_competencia LIMIT 1) AS rendimento_proximo_data
            FROM conta c LEFT JOIN investimento i ON i.conta_id = c.id
            WHERE NOT c.inativa AND (c.tipo = 'investimento' OR i.conta_id IS NOT NULL) ORDER BY c.nome""").fetchall()
    out = []
    for r in rs:
        item = dict(r)
        item["rotulo"] = SUBTIPOS[r["subtipo"]][0] if r["subtipo"] else None
        item["manual"] = bool(r["subtipo"]) and r["indexador"] == "manual"
        if r["configurado"]:
            aliq = aliquota_para(_inv_dict(r), hoje)
            item["aliquota_ir"] = aliq
            prox = r["rendimento_proximo"]
            item["rendimento_proximo_liquido"] = round(prox * (1 - aliq)) if prox else None
            item["dias_para_vencimento"] = (r["data_vencimento"] - hoje).days if r["data_vencimento"] else None
        out.append(item)
    return {"premissas": prem, "investimentos": out}


@router.put("/contas/{cid}/investimento")
def definir(cid: str, body: InvestimentoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    c = cur.execute("SELECT id, tipo, dono_id FROM conta WHERE id = %s", (cid,)).fetchone()
    if not c:
        raise HTTPException(404, "conta não encontrada")
    if c["dono_id"] != usuario.id:
        raise HTTPException(403, "só o dono da conta configura o investimento")
    if c["tipo"] != "investimento":
        raise HTTPException(422, "esta conta não é do tipo investimento")
    _rotulo, idx_padrao, isento_padrao, manual = SUBTIPOS[body.subtipo]
    indexador = body.indexador or idx_padrao
    if manual:
        indexador = "manual"
    if body.subtipo == "poupanca":
        indexador = "poupanca"
    isento = isento_padrao if body.isento_ir is None else body.isento_ir
    if indexador in ("prefixado", "ipca") and body.taxa is None:
        raise HTTPException(422, "informe a taxa")
    if indexador == "cdi" and body.taxa is None:
        raise HTTPException(422, "informe o percentual do CDI")
    dia = None if indexador == "manual" else (body.dia_aniversario or (body.data_aplicacao.day if body.data_aplicacao else None))
    if indexador != "manual" and not dia:
        raise HTTPException(422, "informe o dia de aniversário (dia do mês em que o saldo é atualizado)")
    if body.data_aplicacao and body.data_vencimento and body.data_vencimento < body.data_aplicacao:
        raise HTTPException(422, "o vencimento não pode ser antes da aplicação")
    cur.execute(
        """INSERT INTO investimento(conta_id, subtipo, indexador, taxa, data_aplicacao, dia_aniversario, data_vencimento, isento_ir, alerta_dias)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (conta_id) DO UPDATE SET subtipo = EXCLUDED.subtipo, indexador = EXCLUDED.indexador, taxa = EXCLUDED.taxa,
             data_aplicacao = EXCLUDED.data_aplicacao, dia_aniversario = EXCLUDED.dia_aniversario, data_vencimento = EXCLUDED.data_vencimento,
             isento_ir = EXCLUDED.isento_ir, alerta_dias = EXCLUDED.alerta_dias, atualizado_em = now(),
             aviso_enviado_para = CASE WHEN investimento.data_vencimento IS DISTINCT FROM EXCLUDED.data_vencimento THEN NULL ELSE investimento.aviso_enviado_para END""",
        (cid, body.subtipo, indexador, None if indexador == "manual" else body.taxa, body.data_aplicacao, dia, body.data_vencimento, isento, body.alerta_dias))
    recalcular(cur, usuario, cid)
    return {"ok": True}


@router.post("/investimentos/recalcular")
def recalcular_rota(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return recalcular(cur, usuario)


def recalcular(cur, usuario, conta_id=None) -> dict:
    """Refaz os rendimentos PREVISTOS (mês atual + 5) das contas de investimento do usuário a partir do saldo de hoje, dos movimentos
    previstos e das premissas. O que já foi confirmado não muda e o mês confirmado não é projetado de novo."""
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    prem = _premissas(cur, usuario.id)
    filtro = " AND c.id = %s" if conta_id else ""
    rs = cur.execute(
        f"""SELECT c.id, c.nome, c.data_saldo_inicial, {SALDO} AS saldo, i.indexador, i.taxa, i.dia_aniversario, i.data_vencimento,
                   i.isento_ir, i.data_aplicacao
            FROM conta c JOIN investimento i ON i.conta_id = c.id
            WHERE c.dono_id = %s AND NOT c.inativa AND i.indexador <> 'manual' AND i.dia_aniversario IS NOT NULL{filtro}""",
        (usuario.id, conta_id) if conta_id else (usuario.id,)).fetchall()
    cat = cur.execute("SELECT id FROM categoria WHERE dono_id = %s AND codigo_origem = '1000.07' LIMIT 1", (usuario.id,)).fetchone()
    criados = atualizados = removidos = 0
    for r in rs:
        ajustes = [(t["data_caixa"], t["valor_centavos"]) for t in cur.execute(
            "SELECT data_caixa, valor_centavos FROM transacao WHERE conta_id = %s AND estado = 'previsto' AND origem <> 'rendimento' AND data_caixa >= %s",
            (r["id"], r["data_saldo_inicial"])).fetchall()]
        confirmados = frozenset((t["data_competencia"].year, t["data_competencia"].month) for t in cur.execute(
            "SELECT data_competencia FROM transacao WHERE conta_id = %s AND origem = 'rendimento' AND estado IN ('confirmado','conciliado') AND data_competencia >= %s",
            (r["id"], inicio_mes)).fetchall())
        desejados = {d: v for d, v in projetar(dict(r), prem, r["saldo"], ajustes, hoje, HORIZONTE, confirmados)}   # por data: o último período (até o vencimento) cai no mesmo mês do aniversário
        existentes = {t["data_competencia"]: t for t in cur.execute(
            "SELECT id, data_competencia, valor_centavos FROM transacao WHERE conta_id = %s AND origem = 'rendimento' AND estado = 'previsto' AND data_competencia >= %s",
            (r["id"], inicio_mes)).fetchall()}
        for dt, t in existentes.items():
            if dt not in desejados:
                cur.execute("DELETE FROM transacao WHERE id = %s", (t["id"],))
                removidos += 1
        for d, v in desejados.items():
            t = existentes.get(d)
            if t is None:
                cur.execute(
                    """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, conta_id, categoria_id, descricao, origem)
                       VALUES (%s,'receita','previsto',%s,%s,%s,%s,%s,%s,'rendimento')""",
                    (usuario.id, v, d, d, r["id"], cat["id"] if cat else None, f"Rendimento {r['nome']}"))
                criados += 1
            elif t["valor_centavos"] != v:
                cur.execute("UPDATE transacao SET valor_centavos = %s WHERE id = %s", (v, t["id"]))
                atualizados += 1
    return {"criados": criados, "atualizados": atualizados, "removidos": removidos}


@router.post("/contas/{cid}/atualizar-valor")
def atualizar_valor(cid: str, body: AtualizarValorIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Para investimentos de valor informado à mão (renda variável etc.): lança a diferença entre o valor informado e o saldo atual."""
    c = cur.execute(f"SELECT c.id, c.tipo, c.dono_id, c.nome, {SALDO} AS saldo FROM conta c WHERE c.id = %s", (cid,)).fetchone()
    if not c:
        raise HTTPException(404, "conta não encontrada")
    if c["dono_id"] != usuario.id or c["tipo"] != "investimento":
        raise HTTPException(403, "só o dono atualiza o valor de uma conta de investimento")
    dif = body.valor_centavos - c["saldo"]
    if dif == 0:
        return {"diferenca_centavos": 0}
    dia = body.data or date.today()
    cat = cur.execute("SELECT id FROM categoria WHERE dono_id = %s AND codigo_origem = '1000.07' LIMIT 1", (usuario.id,)).fetchone() if dif > 0 else None
    cur.execute(
        """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, conta_id, categoria_id, descricao, origem)
           VALUES (%s,%s,'confirmado',%s,%s,%s,%s,%s,%s,'manual')""",
        (usuario.id, "receita" if dif > 0 else "despesa", dif, dia, dia, cid, cat["id"] if cat else None, f"Atualização de valor {c['nome']}"))
    return {"diferenca_centavos": dif}


def avisar_vencimentos(hoje: date | None = None, enviar=None) -> int:
    """Rotina diária: e-mail ao DONO da conta quando um investimento está a `alerta_dias` (ou menos) do vencimento. Um aviso por vencimento."""
    hoje = hoje or date.today()
    enviar = enviar or mailer.enviar
    enviados = 0
    with sessao(None) as cur:
        pend = cur.execute("SELECT * FROM investimentos_a_avisar(%s)", (hoje,)).fetchall()
    for p in pend:
        dias = (p["data_vencimento"] - hoje).days
        quando = "hoje" if dias == 0 else "amanhã" if dias == 1 else f"em {dias} dias"
        saldo = f"R$ {p['saldo_centavos'] / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        try:
            enviar(p["dono_email"], f"Seu investimento \"{p['conta_nome']}\" vence {quando}",
                   f"Olá, {p['dono_nome']}.\n\nO investimento \"{p['conta_nome']}\" vence {quando} ({p['data_vencimento']:%d/%m/%Y}). "
                   f"Saldo atual no app: {saldo}.\n\nDecida com antecedência o que fazer com o dinheiro (resgatar, reinvestir). "
                   f"Este aviso é automático e não é recomendação de investimento.")
            with sessao(None) as cur:
                cur.execute("SELECT investimento_avisado(%s, %s)", (p["conta_id"], p["data_vencimento"]))
            enviados += 1
        except Exception:
            log.exception("falha ao avisar vencimento do investimento %s", p["conta_id"])
    return enviados
