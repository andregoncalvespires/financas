"""Kit padrão de categorias (plano de contas enxuto: grupos e categorias de receita e despesa).
Cada novo usuário recebe uma cópia editável. `codigo` é estável e serve de ponte para a IA e para relatórios."""

KIT = [
    ("1000", "Receitas", "receita", [
        "Salário", "13º salário", "Férias", "Abonos, PLR e participação nos resultados", "Horas extras",
        "Adiantamento salarial", "Rendimentos e juros", "Empréstimos recebidos",
        "Reembolsos e compras de terceiros", "Venda de bens", "Restituição de IR", "Outras receitas"]),
    ("2000", "Descontos em folha", "despesa", [
        "INSS", "IRRF", "Previdência privada", "Seguro de vida", "Vale-alimentação", "Desconto de adiantamento", "Outros descontos"]),
    ("2005", "Tarifas bancárias", "despesa", ["Tarifas e manutenção de conta", "Juros e IOF"]),
    ("2010", "Habitação", "despesa", [
        "Aluguel", "Financiamento imobiliário", "Condomínio", "Água e esgoto", "Energia elétrica", "Internet", "Telefone fixo",
        "TV por assinatura e streaming", "Manutenção e reparos", "Faxina e diarista", "Piscina e jardim"]),
    ("2020", "Alimentação", "despesa", [
        "Supermercado", "Padaria e dia a dia", "Hortifruti", "Refeições fora de casa", "Gás de cozinha"]),
    ("2030", "Educação e informação", "despesa", [
        "Escola", "Faculdade", "Pós-graduação", "Cursos e treinamentos", "Idiomas", "Material escolar", "Uniformes",
        "Transporte escolar", "Merenda", "Livros", "Assinaturas de revistas e apps", "Atividades e confraternizações"]),
    ("2040", "Despesas pessoais", "despesa", ["Academia e esporte", "Salão e beleza", "Telefone celular", "Vestuário e calçados"]),
    ("2050", "Transporte", "despesa", [
        "Combustível", "Estacionamento", "Lavagem", "Manutenção do veículo", "Seguro do veículo", "Ônibus e metrô",
        "Táxi e aplicativo", "Pedágio"]),
    ("2060", "Lazer", "despesa", ["Clubes e mensalidades", "Festas", "Bares e restaurantes", "Viagens", "Diversão", "Vinhos e bebidas"]),
    ("2070", "Saúde", "despesa", [
        "Plano de saúde", "Plano odontológico", "Consultas médicas", "Terapias (psicologia, fono, massoterapia)",
        "Dentistas", "Medicamentos", "Exames"]),
    ("2080", "Empregados", "despesa", ["Salários", "Encargos e INSS", "Vale-transporte", "Férias e 13º", "Abonos e horas extras"]),
    ("2090", "Impostos", "despesa", ["IRPF", "IPTU", "IPVA", "Licenciamento e seguro obrigatório", "INSS autônomo", "Outros impostos"]),
    ("2095", "Empréstimos", "despesa", ["Parcela de empréstimo", "Juros de empréstimo", "Empréstimo entre pessoas"]),
    ("2900", "Outras despesas", "despesa", [
        "Presentes", "Eletroeletrônicos", "Móveis e decoração", "Mesada dos filhos", "Animais de estimação", "Doações", "Outras despesas"]),
]


def linhas():
    """(codigo, grupo_codigo, grupo_nome, nome, tipo, ordem)"""
    out = []
    for gcod, gnome, tipo, itens in KIT:
        for i, nome in enumerate(itens, start=1):
            out.append((f"{gcod}.{i:02d}", gcod, gnome, nome, tipo, i))
    return out


def catalogo_para_prompt():
    """Lista compacta 'codigo = Grupo > Nome' usada no prompt de extração do Gemini."""
    return "\n".join(f"{c} = {g} > {n}" for c, _, g, n, _, _ in linhas())
