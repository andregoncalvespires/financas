"""Cálculo (estimativa) do rendimento de investimentos de renda fixa. Funções puras, sem banco.
As taxas são premissas do usuário (CDI, Selic, IPCA, TR). Tudo aqui é uma ESTIMATIVA, não recomendação nem extrato."""
from calendar import monthrange
from datetime import date

SUBTIPOS = {
    # chave: (rótulo, indexador padrão, isento de IR por padrão, valor informado à mão)
    "poupanca": ("Poupança", "poupanca", True, False),
    "tesouro_selic": ("Tesouro Selic", "selic", False, False),
    "tesouro_prefixado": ("Tesouro Prefixado", "prefixado", False, False),
    "tesouro_ipca": ("Tesouro IPCA+", "ipca", False, False),
    "cdb": ("CDB", "cdi", False, False),
    "lci": ("LCI", "cdi", True, False),
    "lca": ("LCA", "cdi", True, False),
    "lc": ("LC (letra de câmbio)", "cdi", False, False),
    "la": ("LA (letra de arrendamento)", "cdi", False, False),
    "debenture": ("Debênture incentivada", "ipca", True, False),
    "cri_cra": ("CRI / CRA", "ipca", True, False),
    "fundo_rf": ("Fundo de renda fixa", "cdi", False, False),
    "previdencia": ("Previdência (PGBL/VGBL)", "manual", False, True),
    "renda_variavel": ("Renda variável (ações, FIIs, ETFs)", "manual", False, True),
    "outro": ("Outro", "manual", False, True),
}

# valores iniciais de exemplo; o usuário ajusta em "Premissas"
PREMISSAS_PADRAO = {"selic": 14.0, "cdi": 13.9, "ipca": 4.5, "tr": 0.0}


def premissas_com_padrao(cfg: dict | None) -> dict:
    p = dict(PREMISSAS_PADRAO)
    for k, v in ((cfg or {}).get("premissas") or {}).items():
        if k in p and isinstance(v, (int, float)):
            p[k] = float(v)
    return p


def aliquota_ir(dias: int) -> float:
    """IR regressivo da renda fixa (pessoa física), sobre o rendimento. Valores configuráveis aqui; confira se a regra mudou."""
    if dias <= 180:
        return 0.225
    if dias <= 360:
        return 0.20
    if dias <= 720:
        return 0.175
    return 0.15


def anual_para_mensal(taxa_aa: float) -> float:
    return (1 + taxa_aa) ** (1 / 12) - 1


def taxa_bruta_aa(indexador: str, taxa: float | None, prem: dict) -> float | None:
    """Taxa efetiva bruta ao ano (fração) para o indexador, ou None quando não há cálculo (valor manual)."""
    t = (taxa or 0.0) / 100
    if indexador == "prefixado":
        return t
    if indexador == "cdi":
        cdi = prem["cdi"] / 100
        diaria = (1 + cdi) ** (1 / 252) - 1
        return (1 + diaria * (taxa if taxa is not None else 100) / 100) ** 252 - 1
    if indexador == "selic":
        return prem["selic"] / 100 + t
    if indexador == "ipca":
        return (1 + prem["ipca"] / 100) * (1 + t) - 1
    return None


def taxa_poupanca_mensal(prem: dict) -> float:
    """Regra vigente: Selic acima de 8,5% a.a. => 0,5% a.m. + TR; até 8,5% => 70% da Selic + TR."""
    tr_m = anual_para_mensal(prem["tr"] / 100)
    base = 0.005 if prem["selic"] > 8.5 else anual_para_mensal(0.7 * prem["selic"] / 100)
    return (1 + base) * (1 + tr_m) - 1


def taxa_periodo(inv: dict, prem: dict, inicio: date, fim: date) -> float:
    """Fração de rendimento bruto entre duas datas (calendário)."""
    if inv["indexador"] == "poupanca":
        return taxa_poupanca_mensal(prem)
    aa = taxa_bruta_aa(inv["indexador"], inv["taxa"] and float(inv["taxa"]), prem)
    if aa is None or fim <= inicio:
        return 0.0
    return (1 + aa) ** ((fim - inicio).days / 365) - 1


def data_do_mes(ano: int, mes: int, dia: int) -> date:
    return date(ano, mes, min(dia, monthrange(ano, mes)[1]))


def mes_mais(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def aliquota_para(inv: dict, hoje: date) -> float:
    """Alíquota de IR estimada hoje (0 para isentos)."""
    if inv.get("isento_ir") or inv["indexador"] == "manual":
        return 0.0
    ini = inv.get("data_aplicacao")
    return aliquota_ir((hoje - ini).days if ini else 0)


def projetar(inv: dict, prem: dict, saldo: int, ajustes: list[tuple[date, int]], hoje: date, meses: int,
             confirmados: frozenset = frozenset()) -> list[tuple[date, int]]:
    """Rendimentos brutos (centavos) por aniversário, do mês atual até `meses` meses, sobre o saldo projetado.
    `ajustes`: movimentos já previstos na conta (aportes, resgates), que mudam a base antes de cada data.
    `confirmados`: meses (ano, mês) cujo rendimento real já foi confirmado (já está no saldo): não são projetados de novo.
    Para no vencimento (o último período é proporcional)."""
    if inv["indexador"] == "manual" or not inv.get("dia_aniversario"):
        return []
    venc = inv.get("data_vencimento")
    out, acumulado = [], 0
    ant = None
    for k in range(meses):
        m = mes_mais(hoje.replace(day=1), k)
        d = data_do_mes(m.year, m.month, inv["dia_aniversario"])
        if venc and d > venc:
            # último período: vai até o vencimento, se o vencimento cair depois do aniversário anterior
            if ant is not None and venc > ant:
                d = venc
            else:
                break
        prev = ant or data_do_mes(mes_mais(m, -1).year, mes_mais(m, -1).month, inv["dia_aniversario"])
        base = saldo + acumulado + sum(v for dt, v in ajustes if dt <= d)
        if (m.year, m.month) in confirmados:
            ant = d
            continue
        if base > 0:
            r = round(base * taxa_periodo(inv, prem, prev, d))
            if r > 0:
                out.append((d, r))
                acumulado += r
        ant = d
        if venc and d >= venc:
            break
    return out


def fim_do_mes(m: date) -> date:
    return date(m.year, m.month, monthrange(m.year, m.month)[1])


def cenario_premissas(prem: dict, delta_pp: float) -> dict:
    """Premissas deslocadas em `delta_pp` pontos percentuais (Selic, CDI e IPCA; nunca abaixo de zero). A TR não muda."""
    p = dict(prem)
    for k in ("selic", "cdi", "ipca"):
        p[k] = max(0.0, prem[k] + delta_pp)
    return p


def serie_mensal(saldo: int, rendimentos: list[tuple[date, int]], ajustes: list[tuple[date, int]], hoje: date, meses: int) -> list[tuple[str, int]]:
    """Saldo ao fim de cada mês, do mês atual até `meses` meses à frente: saldo de hoje + rendimentos + movimentos previstos até a data."""
    out = []
    for k in range(meses + 1):
        fim = fim_do_mes(mes_mais(hoje.replace(day=1), k))
        v = saldo + sum(r for d, r in rendimentos if d <= fim) + sum(a for d, a in ajustes if d <= fim)
        out.append((f"{fim.year}-{fim.month:02d}", v))
    return out


def projetar_conta(inv: dict, prem: dict, saldo: int, ajustes: list[tuple[date, int]], hoje: date, meses: int,
                   confirmados: frozenset = frozenset()) -> dict:
    """Série mensal (bruta) + IR estimado ao fim do horizonte para UMA conta. Conta de valor manual fica parada no saldo atual."""
    rend = projetar(inv, prem, saldo, ajustes, hoje, meses, confirmados)
    serie = serie_mensal(saldo, rend, ajustes, hoje, meses)
    total_rend = sum(r for _, r in rend)
    fim = fim_do_mes(mes_mais(hoje.replace(day=1), meses))
    if inv.get("isento_ir") or inv["indexador"] == "manual":
        aliq = 0.0
    else:
        ini = inv.get("data_aplicacao")
        aliq = aliquota_ir((fim - ini).days if ini else 0)
    ir = round(total_rend * aliq)
    return {"serie": serie, "rendimento_bruto": total_rend, "ir_estimado": ir, "aliquota_ir": aliq,
            "final_bruto": serie[-1][1], "final_liquido": serie[-1][1] - ir}


def simular(inv: dict, prem: dict, saldo: int, ajustes: list[tuple[date, int]], hoje: date, meses: int,
            aporte_inicial: int = 0, aporte_mensal: int = 0, resgate: int = 0, mes_resgate: int | None = None) -> dict:
    """Hipótese: aporte inicial hoje, aporte mensal no dia 1 de cada mês seguinte e um resgate único no mês `mes_resgate` (1..meses).
    Compara com o caminho sem nada disso. Estimativa: o IR do cenário é a alíquota do fim do horizonte sobre o rendimento total."""
    base = projetar_conta(inv, prem, saldo, ajustes, hoje, meses)
    extra = [(hoje, aporte_inicial)] if aporte_inicial else []
    for k in range(1, meses + 1):
        if aporte_mensal:
            extra.append((mes_mais(hoje.replace(day=1), k), aporte_mensal))
    if resgate and mes_resgate:
        extra.append((mes_mais(hoje.replace(day=1), mes_resgate), -resgate))
    hip = projetar_conta(inv, prem, saldo + 0, ajustes + extra, hoje, meses)
    aportado = aporte_inicial + aporte_mensal * meses - (resgate if mes_resgate else 0)
    return {"base": base, "hipotese": hip, "aportado_liquido": aportado,
            "ganho_com_aportes": hip["final_liquido"] - base["final_liquido"] - aportado}
