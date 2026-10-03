from datetime import date, timedelta

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import mailer
from ..config import settings
from ..deps import Usuario, get_db, usuario_atual
from ..schemas import ContaIn, ContaPatch, ConviteContaIn, GerarRecorrenciasIn, RecargaIn, TipoContaIn, TipoContaPatch
from ..servicos import add_months, atualizar, limitar_convites, norm
from .transacoes import gerar as gerar_recorrencias

router = APIRouter(prefix="/api")

SQL_CONTAS = """
SELECT c.id, c.nome, c.tipo, c.tipo_conta_id, tc.nome AS tipo_nome, c.dono_id, u.nome AS dono_nome, c.inativa, c.saldo_inicial_centavos, c.data_saldo_inicial,
       papel_conta(c.id) AS papel,
       r.valor_centavos AS recarga_valor_centavos, r.dia_mes AS recarga_dia, COALESCE(r.competencia_mes, 0) AS recarga_competencia_mes, COALESCE(r.ativa, false) AS recarga_ativa,
       (c.saldo_inicial_centavos + COALESCE((SELECT SUM(t.valor_centavos) FROM transacao t
          WHERE t.conta_id = c.id AND t.estado IN ('confirmado','conciliado') AND t.data_caixa >= c.data_saldo_inicial), 0))::bigint AS saldo_atual
FROM conta c JOIN usuario u ON u.id = c.dono_id
LEFT JOIN tipo_conta tc ON tc.id = c.tipo_conta_id
LEFT JOIN recorrencia r ON r.id = c.recarga_recorrencia_id
"""

TIPOS_PADRAO = [("Conta corrente", "corrente"), ("Investimento", "investimento"),
                ("Dinheiro", "dinheiro"), ("Terceiros", "terceiros"), ("Ticket / Vale", "beneficio")]


def garantir_tipos(cur, uid):
    """Cada usuário recebe os tipos padrão (editáveis) no primeiro acesso."""
    if cur.execute("SELECT 1 FROM tipo_conta WHERE dono_id = %s LIMIT 1", (uid,)).fetchone():
        return
    for nome, classe in TIPOS_PADRAO:
        cur.execute("INSERT INTO tipo_conta(dono_id, nome, nome_norm, classe) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (uid, nome, norm(nome), classe))


@router.get("/tipos-conta")
def listar_tipos(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    garantir_tipos(cur, usuario.id)
    return cur.execute(
        """SELECT tc.id, tc.nome, tc.classe, tc.inativo, tc.dono_id,
                  (SELECT count(*) FROM conta c WHERE c.tipo_conta_id = tc.id)::int AS em_uso
           FROM tipo_conta tc ORDER BY tc.inativo, tc.nome""").fetchall()


@router.post("/tipos-conta", status_code=201)
def criar_tipo(body: TipoContaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    garantir_tipos(cur, usuario.id)
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(422, "informe o nome")
    if cur.execute("SELECT 1 FROM tipo_conta WHERE dono_id = %s AND nome_norm = %s", (usuario.id, norm(nome))).fetchone():
        raise HTTPException(409, "já existe um tipo com este nome")
    return cur.execute("INSERT INTO tipo_conta(dono_id, nome, nome_norm, classe) VALUES (%s,%s,%s,%s) RETURNING id, nome, classe, inativo, dono_id, 0 AS em_uso",
                       (usuario.id, nome, norm(nome), "investimento" if body.classe == "poupanca" else body.classe)).fetchone()


@router.patch("/tipos-conta/{tid}")
def alterar_tipo(tid: str, body: TipoContaPatch, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    t = cur.execute("SELECT id, nome, classe FROM tipo_conta WHERE id = %s AND dono_id = %s", (tid, usuario.id)).fetchone()
    if not t:
        raise HTTPException(404, "tipo não encontrado")
    dados = {}
    if body.nome is not None:
        nome = body.nome.strip()
        if not nome:
            raise HTTPException(422, "informe o nome")
        if cur.execute("SELECT 1 FROM tipo_conta WHERE dono_id = %s AND nome_norm = %s AND id <> %s", (usuario.id, norm(nome), tid)).fetchone():
            raise HTTPException(409, "já existe um tipo com este nome")
        dados.update(nome=nome, nome_norm=norm(nome))
    if body.classe is not None:
        dados["classe"] = "investimento" if body.classe == "poupanca" else body.classe
    if body.inativo is not None:
        dados["inativo"] = body.inativo
    if dados:
        atualizar(cur, "tipo_conta", tid, dados)
        if "classe" in dados:   # o comportamento do tipo vale para todas as contas que o usam
            cur.execute("UPDATE conta SET tipo = %s WHERE tipo_conta_id = %s", (dados["classe"], tid))
    return cur.execute("""SELECT tc.id, tc.nome, tc.classe, tc.inativo, tc.dono_id,
                                 (SELECT count(*) FROM conta c WHERE c.tipo_conta_id = tc.id)::int AS em_uso FROM tipo_conta tc WHERE tc.id = %s""", (tid,)).fetchone()


@router.delete("/tipos-conta/{tid}")
def excluir_tipo(tid: str, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    try:
        with cur.connection.transaction():
            r = cur.execute("DELETE FROM tipo_conta WHERE id = %s AND dono_id = %s RETURNING id", (tid, usuario.id)).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(409, "há contas usando este tipo; inative-o ou mude o tipo dessas contas")
    if not r:
        raise HTTPException(404, "tipo não encontrado")
    return {"ok": True}


def _tipo_valido(cur, tipo_conta_id, dono_id):
    t = cur.execute("SELECT id, classe FROM tipo_conta WHERE id = %s AND dono_id = %s", (tipo_conta_id, dono_id)).fetchone()
    if not t:
        raise HTTPException(422, "tipo de conta inválido")
    return t


def aplicar_recarga(cur, usuario, cid, valor, dia, ativa, competencia_mes=0):
    """Mantém a recorrência de receita que credita o benefício todo mês (valor, dia, ativa).
    Mudar valor/dia vale dos previstos do mês em diante; o que já foi confirmado nunca é alterado."""
    c = cur.execute("SELECT nome, recarga_recorrencia_id FROM conta WHERE id = %s", (cid,)).fetchone()
    hoje = date.today()
    mes_ini = hoje.replace(day=1)
    rec = cur.execute("SELECT * FROM recorrencia WHERE id = %s", (c["recarga_recorrencia_id"],)).fetchone() if c["recarga_recorrencia_id"] else None
    if not rec:
        if not ativa:
            return
        rid = cur.execute(
            """INSERT INTO recorrencia(criado_por, conta_id, tipo, valor_centavos, dia_mes, descricao, inicio, competencia_mes)
               VALUES (%s,%s,'receita',%s,%s,%s,%s,%s) RETURNING id""", (usuario.id, cid, valor, dia, f"Recarga {c['nome']}", hoje, competencia_mes)).fetchone()["id"]
        cur.execute("UPDATE conta SET recarga_recorrencia_id = %s WHERE id = %s", (rid, cid))
    else:
        rid = rec["id"]
        reativou = ativa and not rec["ativa"]
        mudou_dia = rec["dia_mes"] != dia or rec["competencia_mes"] != competencia_mes
        desde = add_months(mes_ini, rec["competencia_mes"])      # os previstos atuais seguem o deslocamento ANTERIOR
        cur.execute("UPDATE recorrencia SET valor_centavos = %s, dia_mes = %s, ativa = %s, competencia_mes = %s, inicio = CASE WHEN %s THEN %s ELSE inicio END WHERE id = %s",
                    (valor, dia, ativa, competencia_mes, reativou or mudou_dia, hoje, rid))
        if not ativa or mudou_dia or reativou:
            cur.execute("DELETE FROM transacao WHERE recorrencia_id = %s AND estado = 'previsto' AND data_competencia >= %s", (rid, desde))
        else:
            cur.execute("UPDATE transacao SET valor_centavos = %s WHERE recorrencia_id = %s AND estado = 'previsto' AND data_competencia >= %s", (valor, rid, desde))
    if ativa:
        gerar_recorrencias(GerarRecorrenciasIn(mes=mes_ini.strftime("%Y-%m")), cur, usuario)
        if hoje.day >= 22:
            prox = (mes_ini.replace(day=28) + timedelta(days=4)).replace(day=1)
            gerar_recorrencias(GerarRecorrenciasIn(mes=prox.strftime("%Y-%m")), cur, usuario)


@router.get("/contas")
def listar(cur=Depends(get_db)):
    return cur.execute(SQL_CONTAS + " ORDER BY c.inativa, c.nome").fetchall()


@router.post("/contas", status_code=201)
def criar(body: ContaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    garantir_tipos(cur, usuario.id)
    if body.tipo_conta_id:
        t = _tipo_valido(cur, body.tipo_conta_id, usuario.id)
    else:
        classe = "investimento" if body.tipo == "poupanca" else body.tipo      # a poupança agora é um subtipo de investimento
        t = cur.execute("SELECT id, classe FROM tipo_conta WHERE dono_id = %s AND classe = %s ORDER BY inativo, criado_em LIMIT 1", (usuario.id, classe)).fetchone()
        if not t:
            raise HTTPException(422, "tipo de conta inválido")
    if (body.recarga_valor_centavos or body.recarga_dia) and t["classe"] != "beneficio":
        raise HTTPException(422, "recarga mensal só existe em contas do comportamento 'benefício'")
    if bool(body.recarga_valor_centavos) != bool(body.recarga_dia):
        raise HTTPException(422, "informe valor e dia da recarga")
    r = cur.execute(
        "INSERT INTO conta(dono_id, nome, tipo, tipo_conta_id, saldo_inicial_centavos, data_saldo_inicial) VALUES (%s,%s,%s,%s,%s,COALESCE(%s, current_date)) RETURNING id",
        (usuario.id, body.nome, t["classe"], t["id"], body.saldo_inicial_centavos, body.data_saldo_inicial)).fetchone()
    if body.recarga_valor_centavos:
        aplicar_recarga(cur, usuario, r["id"], body.recarga_valor_centavos, body.recarga_dia, True, body.recarga_competencia_mes)
    return cur.execute(SQL_CONTAS + " WHERE c.id = %s", (r["id"],)).fetchone()


@router.patch("/contas/{cid}")
def alterar(cid: str, body: ContaPatch, cur=Depends(get_db)):
    dados = body.model_dump()
    tid = dados.pop("tipo_conta_id")
    if tid:
        dono = cur.execute("SELECT dono_id FROM conta WHERE id = %s", (cid,)).fetchone()
        if not dono:
            raise HTTPException(404, "registro não encontrado ou sem permissão")
        t = _tipo_valido(cur, tid, dono["dono_id"])
        dados.update(tipo_conta_id=t["id"], tipo=t["classe"])
    atualizar(cur, "conta", cid, dados)
    return cur.execute(SQL_CONTAS + " WHERE c.id = %s", (cid,)).fetchone()


@router.put("/contas/{cid}/recarga")
def definir_recarga(cid: str, body: RecargaIn, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    c = cur.execute("SELECT tipo, papel_conta(id) AS papel FROM conta WHERE id = %s", (cid,)).fetchone()
    if not c:
        raise HTTPException(404, "conta não encontrada")
    if c["papel"] not in ("dono", "gestor"):
        raise HTTPException(403, "apenas o dono ou gestor altera a recarga")
    if c["tipo"] != "beneficio":
        raise HTTPException(422, "recarga mensal só existe em contas do comportamento 'benefício'")
    aplicar_recarga(cur, usuario, cid, body.valor_centavos, body.dia_mes, body.ativa, body.competencia_mes)
    return cur.execute(SQL_CONTAS + " WHERE c.id = %s", (cid,)).fetchone()


@router.delete("/contas/{cid}")
def excluir(cid: str, cur=Depends(get_db)):
    r = cur.execute("DELETE FROM conta WHERE id = %s RETURNING id", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "conta não encontrada ou você não é o dono")
    return {"ok": True}


@router.get("/contas/{cid}/acessos")
def acessos(cid: str, cur=Depends(get_db)):
    if not cur.execute("SELECT 1 FROM conta WHERE id = %s", (cid,)).fetchone():
        raise HTTPException(404, "conta não encontrada")
    return cur.execute(
        "SELECT a.usuario_id, a.papel, u.nome, u.email::text AS email FROM conta_acesso a JOIN usuario u ON u.id = a.usuario_id WHERE a.conta_id = %s ORDER BY u.nome",
        (cid,)).fetchall()


@router.delete("/contas/{cid}/acessos/{uid}")
def revogar_acesso(cid: str, uid: str, cur=Depends(get_db)):
    r = cur.execute("DELETE FROM conta_acesso WHERE conta_id = %s AND usuario_id = %s RETURNING usuario_id", (cid, uid)).fetchone()
    if not r:
        raise HTTPException(404, "acesso não encontrado ou sem permissão")
    return {"ok": True}


@router.post("/contas/{cid}/convites", status_code=201)
def convidar(cid: str, body: ConviteContaIn, bg: BackgroundTasks, cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    conta = cur.execute("SELECT nome FROM conta WHERE id = %s", (cid,)).fetchone()
    if not conta:
        raise HTTPException(404, "conta não encontrada")
    email = body.email.lower()
    if email == usuario.email.lower():
        raise HTTPException(422, "você não pode convidar a si mesmo")
    limitar_convites(cur, usuario.id)
    r = cur.execute(
        "INSERT INTO convite(tipo, conta_id, email, papel, descricao, criado_por) VALUES ('conta',%s,%s,%s,%s,%s) RETURNING id",
        (cid, email, body.papel, f"Conta {conta['nome']}", usuario.id)).fetchone()
    bg.add_task(mailer.enviar, email, f"{usuario.nome} compartilhou uma conta com você",
                f"{usuario.nome} convidou você para acessar a conta \"{conta['nome']}\" como {body.papel}.\n"
                f"Entre em {settings.app_url} com este e-mail e aceite o convite.")
    return {"id": r["id"]}


@router.get("/convites")
def convites(cur=Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    base = """SELECT v.id, v.tipo, v.email::text AS email, v.papel, v.descricao, v.estado, v.criado_em, v.expira_em,
                     u.nome AS convidado_por_nome
              FROM convite v JOIN usuario u ON u.id = v.criado_por
              WHERE v.estado = 'pendente' AND v.expira_em > now() AND """
    recebidos = cur.execute(base + "v.email::text = meu_email() ORDER BY v.criado_em DESC").fetchall()
    enviados = cur.execute(base + "v.criado_por = %s ORDER BY v.criado_em DESC", (usuario.id,)).fetchall()
    return {"recebidos": recebidos, "enviados": enviados}


@router.post("/convites/{vid}/aceitar")
def aceitar(vid: str, cur=Depends(get_db)):
    return {"tipo": cur.execute("SELECT aceitar_convite(%s) AS t", (vid,)).fetchone()["t"]}


@router.post("/convites/{vid}/recusar")
def recusar(vid: str, cur=Depends(get_db)):
    cur.execute("SELECT recusar_convite(%s)", (vid,))
    return {"ok": True}


@router.post("/convites/{vid}/cancelar")
def cancelar(vid: str, cur=Depends(get_db)):
    r = cur.execute("UPDATE convite SET estado = 'cancelado' WHERE id = %s AND estado = 'pendente' RETURNING id", (vid,)).fetchone()
    if not r:
        raise HTTPException(404, "convite não encontrado")
    return {"ok": True}
