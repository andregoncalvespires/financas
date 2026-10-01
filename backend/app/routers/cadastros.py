from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import Usuario, get_db, usuario_atual
from ..schemas import CategoriaIn, CategoriaPatch, FavorecidoIn, MesclarIn
from ..servicos import atualizar, norm, validar_categoria

router = APIRouter(prefix="/api")


@router.get("/categorias")
def categorias(cur=Depends(get_db)):
    return cur.execute("SELECT id, dono_id, pai_id, nome, tipo, codigo_origem, ativa, ordem FROM categoria ORDER BY dono_id, ordem, nome").fetchall()


def _minha_categoria(cur, cid, uid):
    c = cur.execute("SELECT * FROM categoria WHERE id = %s AND dono_id = %s", (cid, uid)).fetchone()
    if not c:
        raise HTTPException(404, "categoria não encontrada ou não é sua")
    return c


def _existe_nome(cur, uid, pai_id, nome, ignorar=None):
    return cur.execute(
        "SELECT 1 FROM categoria WHERE dono_id = %s AND pai_id IS NOT DISTINCT FROM %s AND lower(nome) = lower(%s) AND id IS DISTINCT FROM %s",
        (uid, pai_id, nome.strip(), ignorar)).fetchone() is not None


_COLS = "id, dono_id, pai_id, nome, tipo, codigo_origem, ativa, ordem"


@router.post("/categorias", status_code=201)
def criar_categoria(body: CategoriaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    nome = body.nome.strip()
    if body.pai_id:
        pai = cur.execute("SELECT id, tipo FROM categoria WHERE id = %s AND dono_id = %s AND pai_id IS NULL", (body.pai_id, usuario.id)).fetchone()
        if not pai:
            raise HTTPException(422, "o grupo (pai) deve ser um dos seus grupos de categoria")
        tipo, ordem = pai["tipo"], 999
    else:
        if not body.tipo:
            raise HTTPException(422, "informe o tipo (despesa ou receita) para criar um grupo")
        tipo = body.tipo
        ordem = cur.execute("SELECT COALESCE(max(ordem), 0)::int + 10 AS o FROM categoria WHERE dono_id = %s AND pai_id IS NULL", (usuario.id,)).fetchone()["o"]
    if _existe_nome(cur, usuario.id, body.pai_id, nome):
        raise HTTPException(409, "já existe uma categoria com este nome neste nível")
    return cur.execute(f"INSERT INTO categoria(dono_id, pai_id, nome, tipo, ordem) VALUES (%s,%s,%s,%s,%s) RETURNING {_COLS}",
                       (usuario.id, body.pai_id, nome, tipo, ordem)).fetchone()


@router.patch("/categorias/{cid}")
def alterar_categoria(cid: str, body: CategoriaPatch, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    c = _minha_categoria(cur, cid, usuario.id)
    dados = {"nome": body.nome.strip() if body.nome else None, "ativa": body.ativa}
    novo_pai = body.pai_id
    if novo_pai:
        if not c["pai_id"]:
            raise HTTPException(422, "grupos não podem ser movidos para dentro de outro grupo")
        g = cur.execute("SELECT id, tipo FROM categoria WHERE id = %s AND dono_id = %s AND pai_id IS NULL", (novo_pai, usuario.id)).fetchone()
        if not g:
            raise HTTPException(422, "o destino deve ser um dos seus grupos")
        if g["tipo"] != c["tipo"]:
            raise HTTPException(422, "só é possível mover entre grupos do mesmo tipo (despesa com despesa, receita com receita)")
        dados["pai_id"] = novo_pai
    if dados["nome"] and _existe_nome(cur, usuario.id, novo_pai or c["pai_id"], dados["nome"], ignorar=c["id"]):
        raise HTTPException(409, "já existe uma categoria com este nome neste nível")
    atualizar(cur, "categoria", cid, dados)
    return cur.execute(f"SELECT {_COLS} FROM categoria WHERE id = %s", (cid,)).fetchone()


@router.delete("/categorias/{cid}")
def excluir_categoria(cid: str, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    c = _minha_categoria(cur, cid, usuario.id)
    filhos = cur.execute("SELECT count(*)::int AS n FROM categoria WHERE pai_id = %s", (cid,)).fetchone()["n"]
    if filhos:
        raise HTTPException(409, f"Este grupo tem {filhos} subcategoria(s). Mova-as ou exclua-as antes.")
    lanc = cur.execute("SELECT count(*)::int AS n FROM transacao WHERE categoria_id = %s", (cid,)).fetchone()["n"]
    rec = cur.execute("SELECT count(*)::int AS n FROM recorrencia WHERE categoria_id = %s", (cid,)).fetchone()["n"]
    if lanc or rec:
        raise HTTPException(409, f"Categoria em uso ({lanc} lançamento(s), {rec} recorrência(s)). Mescle em outra categoria ou oculte-a.")
    cur.execute("DELETE FROM categoria WHERE id = %s", (cid,))
    return {"ok": True}


@router.post("/categorias/{cid}/mesclar")
def mesclar_categoria(cid: str, body: MesclarIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Passa tudo da categoria de origem (lançamentos, recorrências, favorecidos, orçamento, código da IA) para o destino e a exclui."""
    o = _minha_categoria(cur, cid, usuario.id)
    d = _minha_categoria(cur, str(body.destino_id), usuario.id)
    if o["id"] == d["id"]:
        raise HTTPException(422, "escolha uma categoria de destino diferente")
    if o["tipo"] != d["tipo"]:
        raise HTTPException(422, "só é possível mesclar categorias do mesmo tipo")
    if not o["pai_id"]:
        raise HTTPException(422, "mescle subcategorias; um grupo vazio pode ser excluído")
    if cur.execute("SELECT 1 FROM categoria WHERE pai_id = %s LIMIT 1", (cid,)).fetchone():
        raise HTTPException(422, "a categoria de origem tem subcategorias")
    total = cur.execute("SELECT count(*)::int AS n FROM transacao WHERE categoria_id = %s", (cid,)).fetchone()["n"]
    movidos = cur.execute("UPDATE transacao SET categoria_id = %s WHERE categoria_id = %s", (d["id"], cid)).rowcount
    if movidos != total:
        raise HTTPException(403, "sem permissão para reclassificar todos os lançamentos desta categoria")
    cur.execute("UPDATE recorrencia SET categoria_id = %s WHERE categoria_id = %s", (d["id"], cid))
    cur.execute("UPDATE favorecido SET categoria_padrao_id = %s WHERE categoria_padrao_id = %s", (d["id"], cid))
    # orçamento da origem passa para o destino; se coincidir início e tipo de regra, somam-se os valores
    for cond in ("modo = 'mes'", "modo <> 'mes'"):
        cur.execute(f"""INSERT INTO orcamento(dono_id, categoria_id, modo, inicio, fim, ocorrencias, meses, valor_centavos)
                       SELECT dono_id, %s, modo, inicio, fim, ocorrencias, meses, valor_centavos FROM orcamento WHERE categoria_id = %s AND {cond}
                       ON CONFLICT (categoria_id, inicio) WHERE {cond}
                       DO UPDATE SET valor_centavos = orcamento.valor_centavos + EXCLUDED.valor_centavos, atualizado_em = now()""",
                    (d["id"], cid))
    codigos = set(d["codigos_alias"]) | set(o["codigos_alias"]) | ({o["codigo_origem"]} if o["codigo_origem"] else set())
    codigos.discard(d["codigo_origem"])
    cur.execute("UPDATE categoria SET codigos_alias = %s WHERE id = %s", (sorted(codigos), d["id"]))
    cur.execute("DELETE FROM categoria WHERE id = %s", (cid,))
    return {"ok": True, "lancamentos_movidos": movidos}


@router.get("/favorecidos")
def favorecidos(q: str = Query(default="", max_length=60), dono_id: str | None = None, cur=Depends(get_db)):
    sql = "SELECT id, dono_id, nome, categoria_padrao_id FROM favorecido WHERE nome_norm LIKE %s"
    params: list = [f"%{norm(q)}%"]
    if dono_id:
        sql += " AND dono_id = %s"
        params.append(dono_id)
    return cur.execute(sql + " ORDER BY nome LIMIT 50", params).fetchall()


@router.post("/favorecidos", status_code=201)
def criar_favorecido(body: FavorecidoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    dono = body.dono_id or usuario.id
    if body.categoria_padrao_id:
        validar_categoria(cur, body.categoria_padrao_id, dono)
    return cur.execute(
        """INSERT INTO favorecido(dono_id, nome, nome_norm, categoria_padrao_id) VALUES (%s,%s,%s,%s)
           ON CONFLICT (dono_id, nome_norm) DO UPDATE SET nome = favorecido.nome RETURNING id, dono_id, nome, categoria_padrao_id""",
        (dono, body.nome.strip(), norm(body.nome), body.categoria_padrao_id)).fetchone()
