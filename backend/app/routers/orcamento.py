from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import Usuario, get_db, usuario_atual
from ..schemas import OrcamentoIn
from ..servicos import add_months, mes_intervalo

router = APIRouter(prefix="/api")

# Realizado = confirmado/conciliado; previsto = ainda por acontecer. Sempre por data de competência.
_VALOR = "CASE WHEN t.tipo = 'despesa' THEN -t.valor_centavos ELSE t.valor_centavos END"


def _aplica(r, m: date) -> bool:
    """A regra de orçamento vale no mês `m` (dia 1)?"""
    if m < r["inicio"]:
        return False
    modo = r["modo"]
    if modo == "mes":
        return m == r["inicio"]
    if modo == "ocorrencias":
        return (m.year - r["inicio"].year) * 12 + m.month - r["inicio"].month < r["ocorrencias"]
    if r["fim"] and m > r["fim"]:
        return False
    if modo == "meses":
        return m.month in r["meses"]
    return True


def _resolver(regras, m: date):
    """Ajuste do mês vence; senão a regra aplicável de início mais recente."""
    ap = [r for r in regras if _aplica(r, m)]
    mes = [r for r in ap if r["modo"] == "mes"]
    if mes:
        return mes[0]
    return max(ap, key=lambda r: r["inicio"]) if ap else None


def _resumo_regra(r):
    if not r:
        return None
    ym = lambda d: d.strftime("%Y-%m") if d and d.year > 2000 else None
    return {"id": r["id"], "modo": r["modo"], "inicio": ym(r["inicio"]), "fim": ym(r["fim"]), "ocorrencias": r["ocorrencias"],
            "meses": r["meses"], "valor_centavos": r["valor_centavos"]}


_COLS_REGRA = "id, categoria_id, modo, inicio, fim, ocorrencias, meses, valor_centavos"


def _grupo_vazio(g):
    return {"id": g["id"], "nome": g["nome"], "orcado": 0, "realizado": 0, "previsto": 0, "categorias": []}


@router.get("/orcamento/donos")
def donos(cur=Depends(get_db)):
    """Donos de cadastro cujas categorias eu enxergo (eu mesmo e quem compartilha contas/cartões comigo)."""
    return cur.execute("SELECT DISTINCT u.id, u.nome FROM categoria c JOIN usuario u ON u.id = c.dono_id ORDER BY u.nome").fetchall()


@router.get("/orcamento")
def orcamento(mes: str = Query(pattern=r"^\d{4}-\d{2}$"), dono_id: str | None = None, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Orçado × realizado × previsto por categoria do dono (competência). Quem só consulta vê o realizado
    apenas dos lançamentos que já enxerga (as regras de acesso valem também aqui)."""
    dono = str(dono_id or usuario.id)
    ini, fim = mes_intervalo(mes)
    cats = cur.execute("SELECT id, pai_id, nome, tipo, ativa FROM categoria WHERE dono_id = %s ORDER BY ordem, nome", (dono,)).fetchall()
    if not cats and dono != str(usuario.id):
        raise HTTPException(404, "orçamento não encontrado")
    nome_dono = cur.execute("SELECT nome FROM usuario WHERE id = %s", (dono,)).fetchone()
    regras: dict = {}
    for r in cur.execute(f"SELECT {_COLS_REGRA} FROM orcamento WHERE dono_id = %s", (dono,)).fetchall():
        regras.setdefault(r["categoria_id"], []).append(r)
    vigente = {cid: _resolver(rs, ini) for cid, rs in regras.items()}
    real = {r["categoria_id"]: r for r in cur.execute(
        f"""SELECT t.categoria_id,
                   COALESCE(SUM({_VALOR}) FILTER (WHERE t.estado IN ('confirmado','conciliado')), 0)::bigint AS realizado,
                   COALESCE(SUM({_VALOR}) FILTER (WHERE t.estado = 'previsto'), 0)::bigint AS previsto
            FROM transacao t WHERE t.tipo IN ('despesa','receita') AND t.data_competencia BETWEEN %s AND %s
              AND t.categoria_id = ANY(%s) GROUP BY 1""", (ini, fim, [c["id"] for c in cats])).fetchall()}
    pode_editar = dono == str(usuario.id)

    def linha(c):
        r = real.get(c["id"], {})
        v = vigente.get(c["id"])
        rs = regras.get(c["id"], [])
        return {"id": c["id"], "nome": c["nome"], "ativa": c["ativa"], "orcado": v["valor_centavos"] if v else 0,
                "regra": _resumo_regra(v), "n_regras": len(rs), "tem_padrao": any(x["modo"] != "mes" for x in rs),
                "especifico": bool(v and v["modo"] == "mes"), "realizado": r.get("realizado", 0), "previsto": r.get("previsto", 0)}

    out = {"mes": mes, "dono_id": dono, "dono_nome": nome_dono["nome"] if nome_dono else "", "pode_editar": pode_editar}
    for tipo, chave in (("receita", "receitas"), ("despesa", "despesas")):
        grupos, tot = [], {"orcado": 0, "realizado": 0, "previsto": 0}
        for g in [c for c in cats if c["tipo"] == tipo and not c["pai_id"]]:
            gg = _grupo_vazio(g)
            gg["ativa"] = g["ativa"]
            propria = linha(g)
            for c in [x for x in cats if x["pai_id"] == g["id"]]:
                l = linha(c)
                relevante = any((l["orcado"], l["realizado"], l["previsto"]))
                if relevante or (pode_editar and c["ativa"] and g["ativa"]):
                    gg["categorias"].append(l)
                    for k in ("orcado", "realizado", "previsto"):
                        gg[k] += l[k]
            if any((propria["orcado"], propria["realizado"], propria["previsto"])):
                propria["nome"] = f"{g['nome']} (sem subcategoria)"
                gg["categorias"].insert(0, propria)
                for k in ("orcado", "realizado", "previsto"):
                    gg[k] += propria[k]
            if gg["categorias"]:
                grupos.append(gg)
                for k in tot:
                    tot[k] += gg[k]
        out[chave] = {**tot, "grupos": grupos}
    return out


@router.get("/orcamento/regras")
def regras_da_categoria(categoria_id: str, cur=Depends(get_db)):
    """Todas as regras de vigência de uma categoria (para editar/remover)."""
    rs = cur.execute(f"SELECT {_COLS_REGRA} FROM orcamento WHERE categoria_id = %s ORDER BY modo = 'mes', inicio", (categoria_id,)).fetchall()
    return [_resumo_regra(r) | {"fim": r["fim"].strftime("%Y-%m") if r["fim"] else None} for r in rs]


@router.put("/orcamento")
def definir(body: OrcamentoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    for it in body.itens:
        if not cur.execute("SELECT 1 FROM categoria WHERE id = %s AND dono_id = %s", (it.categoria_id, usuario.id)).fetchone():
            raise HTTPException(422, "só é possível orçar as suas próprias categorias")
        if not it.inicio and it.modo != "continuo":
            raise HTTPException(422, "informe o mês de início")
        inicio = mes_intervalo(it.inicio)[0] if it.inicio else date(2000, 1, 1)
        fim = mes_intervalo(it.fim)[0] if it.fim else None
        if it.modo == "mes":
            cur.execute("""INSERT INTO orcamento(dono_id, categoria_id, modo, inicio, valor_centavos) VALUES (%s,%s,'mes',%s,%s)
                           ON CONFLICT (categoria_id, inicio) WHERE modo = 'mes'
                           DO UPDATE SET valor_centavos = EXCLUDED.valor_centavos, atualizado_em = now()""",
                        (usuario.id, it.categoria_id, inicio, it.valor_centavos))
        else:
            cur.execute("""INSERT INTO orcamento(dono_id, categoria_id, modo, inicio, fim, ocorrencias, meses, valor_centavos) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (categoria_id, inicio) WHERE modo <> 'mes'
                           DO UPDATE SET valor_centavos = EXCLUDED.valor_centavos, modo = EXCLUDED.modo, fim = EXCLUDED.fim,
                                         ocorrencias = EXCLUDED.ocorrencias, meses = EXCLUDED.meses, atualizado_em = now()""",
                        (usuario.id, it.categoria_id, it.modo, inicio, fim, it.ocorrencias, it.meses, it.valor_centavos))
    return {"ok": True, "itens": len(body.itens)}


@router.delete("/orcamento")
def remover(categoria_id: str | None = None, mes: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"), regra_id: str | None = None,
            cur=Depends(get_db)):
    """Remove uma regra (`regra_id`), o ajuste de um mês (`mes`) ou, sem os dois, todas as regras de vigência da categoria."""
    if regra_id:
        n = cur.execute("DELETE FROM orcamento WHERE id = %s", (regra_id,)).rowcount
    elif not categoria_id:
        raise HTTPException(422, "informe regra_id ou categoria_id")
    elif mes:
        n = cur.execute("DELETE FROM orcamento WHERE categoria_id = %s AND modo = 'mes' AND inicio = %s", (categoria_id, mes_intervalo(mes)[0])).rowcount
    else:
        n = cur.execute("DELETE FROM orcamento WHERE categoria_id = %s AND modo <> 'mes'", (categoria_id,)).rowcount
    if not n:
        raise HTTPException(404, "orçamento não encontrado")
    return {"ok": True}


@router.get("/orcamento/media")
def media(meses: int = Query(3, ge=1, le=12), cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Sugestão: média mensal realizada por categoria nos últimos N meses fechados (por competência)."""
    hoje = date.today()
    fim = date(hoje.year, hoje.month, 1)
    ini = add_months(fim, -meses)
    rows = cur.execute(
        f"""SELECT t.categoria_id, (SUM({_VALOR}) / %s)::bigint AS valor
            FROM transacao t JOIN categoria c ON c.id = t.categoria_id AND c.dono_id = %s
            WHERE t.tipo IN ('despesa','receita') AND t.estado IN ('confirmado','conciliado')
              AND t.data_competencia >= %s AND t.data_competencia < %s GROUP BY 1 HAVING SUM({_VALOR}) > 0""",
        (meses, usuario.id, ini, fim)).fetchall()
    return [{"categoria_id": r["categoria_id"], "valor_centavos": int(round(r["valor"] / 100.0)) * 100} for r in rows]
