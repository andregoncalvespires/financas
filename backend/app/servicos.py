import re
import unicodedata
from calendar import monthrange
from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException

from .schemas import TransacaoIn


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().casefold()


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, monthrange(ano, mes)[1]))


def mes_intervalo(mes: str) -> tuple[date, date]:
    ano, m = int(mes[:4]), int(mes[5:7])
    return date(ano, m, 1), date(ano, m, monthrange(ano, m)[1])


def dono_do_alvo(cur, conta_id, plastico_id) -> UUID:
    if bool(conta_id) == bool(plastico_id):
        raise HTTPException(422, "informe conta_id ou plastico_id (apenas um)")
    if conta_id:
        r = cur.execute("SELECT dono_id FROM conta WHERE id = %s", (conta_id,)).fetchone()
    else:
        r = cur.execute("SELECT k.dono_id FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE p.id = %s", (plastico_id,)).fetchone()
    if not r:
        raise HTTPException(404, "conta/cartão não encontrado")
    return r["dono_id"]


def obter_ou_criar_favorecido(cur, dono_id: UUID, nome: str) -> UUID:
    n = norm(nome)
    r = cur.execute("SELECT id FROM favorecido WHERE dono_id = %s AND nome_norm = %s", (dono_id, n)).fetchone()
    if r:
        return r["id"]
    return cur.execute("INSERT INTO favorecido(dono_id, nome, nome_norm) VALUES (%s,%s,%s) RETURNING id",
                       (dono_id, nome.strip(), n)).fetchone()["id"]


def validar_categoria(cur, cat_id: UUID, dono_id: UUID):
    r = cur.execute("SELECT id FROM categoria WHERE id = %s AND dono_id = %s", (cat_id, dono_id)).fetchone()
    if not r:
        raise HTTPException(422, "categoria inválida: use as categorias do dono da conta/cartão")


LIMITE_CONVITES_DIA = 20


def limitar_convites(cur, usuario_id) -> None:
    """Freio contra abuso do envio de e-mails: no máximo 20 convites por pessoa a cada 24 horas."""
    n = cur.execute("SELECT count(*)::int AS n FROM convite WHERE criado_por = %s AND criado_em > now() - interval '24 hours'", (usuario_id,)).fetchone()["n"]
    if n >= LIMITE_CONVITES_DIA:
        raise HTTPException(429, f"limite de {LIMITE_CONVITES_DIA} convites por dia atingido")


def resolver_favorecido_categoria(cur, dono_id, favorecido_id, favorecido_nome, categoria_id):
    fav_id = favorecido_id
    if not fav_id and favorecido_nome and favorecido_nome.strip():
        fav_id = obter_ou_criar_favorecido(cur, dono_id, favorecido_nome)
    if fav_id:
        f = cur.execute("SELECT categoria_padrao_id FROM favorecido WHERE id = %s AND dono_id = %s", (fav_id, dono_id)).fetchone()
        if not f:
            raise HTTPException(422, "favorecido inválido para este dono")
        if not categoria_id:
            categoria_id = f["categoria_padrao_id"]
    if categoria_id:
        validar_categoria(cur, categoria_id, dono_id)
    return fav_id, categoria_id


def aprender_categoria(cur, fav_id, cat_id):
    """Depois de confirmada, a categoria passa a ser a sugerida para o favorecido."""
    if fav_id and cat_id:
        cur.execute("UPDATE favorecido SET categoria_padrao_id = %s WHERE id = %s", (cat_id, fav_id))


def _valores_parcelas(total: int, n: int) -> list[int]:
    base, resto = divmod(total, n)
    return [base + (1 if i < resto else 0) for i in range(n)]


def criar_transacoes(cur, uid: UUID, b: TransacaoIn, recorrencia_id=None) -> list[dict]:
    dono = dono_do_alvo(cur, b.conta_id, b.plastico_id)
    fav_id, cat_id = resolver_favorecido_categoria(cur, dono, b.favorecido_id, b.favorecido_nome, b.categoria_id)
    sinal = -1 if b.tipo == "despesa" else 1
    n = b.parcelas
    parc_id = uuid4() if n > 1 else None
    forma = b.forma_pagamento or ("cartao" if b.plastico_id else None)
    criadas = []
    for i, valor in enumerate(_valores_parcelas(b.valor_centavos, n)):
        mes_i = add_months(b.data_competencia, i)          # mês da parcela (define a fatura e a data de caixa)
        # competência: cada parcela no seu mês ('parcela') ou a compra inteira no mês da compra ('compra')
        comp = b.data_competencia if (b.competencia_parcelas == "compra" and b.plastico_id) else mes_i
        # compra em cartão já aconteceu por inteiro; nas parcelas de conta/recorrência as futuras ficam previstas
        estado = b.estado if (i == 0 or (b.plastico_id and b.competencia_parcelas == "compra")) else "previsto"
        fatura_id = None
        data_compra = None
        if b.plastico_id:
            f = cur.execute("SELECT * FROM fatura_para_compra(%s, %s)", (b.plastico_id, mes_i)).fetchone()
            fatura_id, data_caixa, data_compra = f["fatura_id"], f["data_vencimento"], b.data_competencia
        else:
            data_caixa = add_months(b.data_caixa or b.data_competencia, i)
        r = cur.execute(
            """INSERT INTO transacao(criado_por, tipo, estado, valor_centavos, data_competencia, data_caixa, data_compra,
                 conta_id, plastico_id, fatura_id, forma_pagamento, categoria_id, favorecido_id, descricao,
                 parcelamento_id, numero_parcela, total_parcelas, recorrencia_id, origem, anexo_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (uid, b.tipo, estado, sinal * valor, comp, data_caixa, data_compra, b.conta_id, b.plastico_id, fatura_id,
             forma, cat_id, fav_id, b.descricao, parc_id, (i + 1) if n > 1 else None, n if n > 1 else None,
             recorrencia_id, b.origem, b.anexo_id if i == 0 else None)).fetchone()
        criadas.append(r)
    if b.estado == "confirmado":
        aprender_categoria(cur, fav_id, cat_id)
    return criadas


def atualizar(cur, tabela: str, id_, dados: dict, extra_where: str = "", nulos: set | frozenset = frozenset()):
    """UPDATE dinâmico apenas com os campos enviados (nomes de tabela/coluna vêm do código, nunca do cliente).
    `nulos` lista campos que podem ser gravados como NULL quando enviados explicitamente."""
    dados = {k: v for k, v in dados.items() if v is not None or k in nulos}
    if not dados:
        r = cur.execute(f"SELECT * FROM {tabela} WHERE id = %s", (id_,)).fetchone()
    else:
        sets = ", ".join(f"{k} = %s" for k in dados)
        r = cur.execute(f"UPDATE {tabela} SET {sets} WHERE id = %s {extra_where} RETURNING *", (*dados.values(), id_)).fetchone()
    if not r:
        raise HTTPException(404, "registro não encontrado ou sem permissão")
    return r
