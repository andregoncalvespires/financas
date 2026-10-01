import hashlib
import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import gemini
from ..config import settings
from ..db import sessao
from ..deps import Usuario, get_db, usuario_atual
from ..imagens import preparar
from ..schemas import TransacaoIn
from ..servicos import criar_transacoes, norm

router = APIRouter(prefix="/api")
MAX_BYTES = 12 * 1024 * 1024
FORMA = {"credito": "cartao", "debito": "debito", "pix": "pix", "dinheiro": "dinheiro", "boleto": "boleto", "transferencia": "ted"}


def _data_valida(s: str) -> date:
    try:
        d = date.fromisoformat(s)
        if abs((d - date.today()).days) < 400:
            return d
    except ValueError:
        pass
    return date.today()


def montar_sugestao(cur, uid, ext: gemini.Extracao) -> dict:
    alertas: list[str] = []
    forma = FORMA.get(ext.forma_pagamento)
    plastico = conta = None
    dono = uid
    if ext.final_cartao:
        pls = cur.execute("""SELECT p.id, p.final, p.rotulo, k.nome AS cartao_nome, k.dono_id FROM plastico p JOIN cartao k ON k.id = p.cartao_id
                             WHERE p.ativo AND p.final = %s ORDER BY p.principal DESC""", (ext.final_cartao,)).fetchall()
        if pls:
            plastico = pls[0]
            if len(pls) > 1:
                alertas.append("mais de um cartão termina com esses dígitos: confirme")
        else:
            alertas.append(f"nenhum cartão seu termina em {ext.final_cartao}")
    if not plastico and ext.forma_pagamento == "credito":
        pls = cur.execute("""SELECT p.id, p.final, p.rotulo, k.nome AS cartao_nome, k.dono_id FROM plastico p JOIN cartao k ON k.id = p.cartao_id
                             WHERE p.ativo""").fetchall()
        if len(pls) == 1:
            plastico = pls[0]
            alertas.append("cartão assumido por ser o único: confirme")
    if plastico:
        dono = plastico["dono_id"]
    else:
        r = cur.execute("SELECT conta_id FROM transacao WHERE criado_por = %s AND conta_id IS NOT NULL ORDER BY criado_em DESC LIMIT 1", (uid,)).fetchone()
        if r:
            conta = cur.execute("SELECT id, dono_id FROM conta WHERE id = %s", (r["conta_id"],)).fetchone()
        if not conta:
            conta = cur.execute("SELECT id, dono_id FROM conta WHERE dono_id = %s AND NOT inativa ORDER BY criado_em LIMIT 1", (uid,)).fetchone()
        if conta:
            dono = conta["dono_id"]
        else:
            alertas.append("cadastre uma conta para lançar")
    fav = None
    n = norm(ext.estabelecimento)
    if n:
        fav = cur.execute("SELECT id, nome, categoria_padrao_id FROM favorecido WHERE dono_id = %s AND (nome_norm = %s OR (length(nome_norm) >= 5 AND %s LIKE nome_norm || '%%')) ORDER BY length(nome_norm) DESC LIMIT 1",
                          (dono, n, n)).fetchone()
    cat = fav["categoria_padrao_id"] if fav else None
    if not cat and ext.categoria_codigo:
        r = cur.execute("SELECT id FROM categoria WHERE dono_id = %s AND ativa AND (codigo_origem = %s OR %s = ANY(codigos_alias)) ORDER BY (codigo_origem = %s) DESC NULLS LAST LIMIT 1", (dono, ext.categoria_codigo, ext.categoria_codigo, ext.categoria_codigo)).fetchone()
        cat = r["id"] if r else None
    valor = round(ext.valor_total * 100)
    data = _data_valida(ext.data)
    dup = bool(valor and cur.execute(
        "SELECT 1 FROM transacao WHERE abs(valor_centavos) = %s AND data_competencia BETWEEN %s AND %s LIMIT 1",
        (valor, data - timedelta(days=1), data + timedelta(days=1))).fetchone())
    if dup:
        alertas.append("já existe lançamento com o mesmo valor e data: pode ser duplicado")
    if not valor:
        alertas.append("não consegui ler o valor")
    if ext.confianca and ext.confianca < 0.6:
        alertas.append("leitura com baixa confiança: revise os campos")
    return {
        "tipo": "receita" if ext.direcao == "entrada" else "despesa", "valor_centavos": valor, "data_competencia": data.isoformat(),
        "descricao": ext.descricao[:200], "favorecido_nome": (fav["nome"] if fav else ext.estabelecimento.strip()), "favorecido_id": fav["id"] if fav else None,
        "categoria_id": cat, "conta_id": conta["id"] if conta else None, "plastico_id": plastico["id"] if plastico else None,
        "plastico_rotulo": (f"{plastico['cartao_nome']} ·· {plastico['final']}" if plastico else None),
        "forma_pagamento": forma, "parcelas": ext.parcelas, "confianca": ext.confianca,
        "tipo_documento": ext.tipo_documento, "possivel_duplicada": dup, "alertas": alertas,
    }


@router.post("/capturas", status_code=201)
def criar(arquivo: UploadFile = File(...), usuario: Usuario = Depends(usuario_atual)):
    bruto = arquivo.file.read(MAX_BYTES + 1)
    if len(bruto) > MAX_BYTES:
        raise HTTPException(413, "arquivo maior que 12 MB")
    dados, mime, ext = preparar(bruto)
    with sessao(usuario.id) as cur:
        n = cur.execute("SELECT count(*) AS n FROM captura WHERE criado_por = %s AND criado_em > now() - interval '24 hours'", (usuario.id,)).fetchone()["n"]
        if n >= settings.capturas_por_dia:
            raise HTTPException(429, f"limite de {settings.capturas_por_dia} leituras por dia atingido")
        rel = f"anexos/{date.today():%Y}/{uuid.uuid4()}.{ext}"
        destino = Path(settings.dados_dir) / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
        anexo = cur.execute("INSERT INTO anexo(criado_por, caminho, mime, sha256, tamanho) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                            (usuario.id, rel, mime, hashlib.sha256(dados).hexdigest(), len(dados))).fetchone()
        cap = cur.execute("INSERT INTO captura(criado_por, anexo_id) VALUES (%s,%s) RETURNING id", (usuario.id, anexo["id"])).fetchone()
    # chamada externa fora da transação do banco
    try:
        extracao, meta = gemini.extrair(dados, mime)
        erro = None
    except gemini.GeminiErro as e:
        extracao, meta, erro = None, {}, str(e)
    with sessao(usuario.id) as cur:
        if erro:
            cur.execute("UPDATE captura SET status = 'erro', erro = %s WHERE id = %s", (erro[:500], cap["id"]))
        else:
            sug = montar_sugestao(cur, usuario.id, extracao)
            cur.execute("UPDATE captura SET resultado = %s::jsonb, sugestao = %s::jsonb, modelo = %s WHERE id = %s",
                        (extracao.model_dump_json(), json.dumps(sug, default=str), meta.get("modelo"), cap["id"]))
        return cur.execute("SELECT id, status, sugestao, erro, anexo_id, criado_em FROM captura WHERE id = %s", (cap["id"],)).fetchone()


@router.get("/capturas")
def listar(status: str = "pendente", cur=Depends(get_db)):
    return cur.execute("SELECT id, status, sugestao, erro, anexo_id, criado_em FROM captura WHERE status = %s ORDER BY criado_em DESC LIMIT 50", (status,)).fetchall()


@router.post("/capturas/{cid}/confirmar", status_code=201)
def confirmar(cid: str, body: TransacaoIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    cap = cur.execute("SELECT id, status, anexo_id FROM captura WHERE id = %s FOR UPDATE", (cid,)).fetchone()
    if not cap or cap["status"] not in ("pendente", "erro"):
        raise HTTPException(404, "captura não encontrada ou já tratada")
    body.origem = "foto"
    body.anexo_id = cap["anexo_id"]
    criadas = criar_transacoes(cur, usuario.id, body)
    cur.execute("UPDATE captura SET status = 'confirmada', transacao_id = %s WHERE id = %s", (criadas[0]["id"], cid))
    return {"transacoes": [c["id"] for c in criadas]}


@router.delete("/capturas/{cid}")
def descartar(cid: str, cur=Depends(get_db)):
    r = cur.execute("UPDATE captura SET status = 'descartada' WHERE id = %s AND status IN ('pendente','erro') RETURNING id", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "captura não encontrada")
    return {"ok": True}


@router.get("/anexos/{aid}")
def anexo(aid: str, cur=Depends(get_db)):
    a = cur.execute("SELECT caminho, mime FROM anexo WHERE id = %s", (aid,)).fetchone()
    if not a:
        raise HTTPException(404, "anexo não encontrado")
    base = Path(settings.dados_dir).resolve()
    arq = (base / a["caminho"]).resolve()
    if base not in arq.parents or not arq.exists():
        raise HTTPException(404, "arquivo indisponível")
    return FileResponse(arq, media_type=a["mime"], headers={"Cache-Control": "private, max-age=3600"})
