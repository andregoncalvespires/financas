import { h, GET, POST, PATCH, brl, aviso, acao, mesISO, somarMes, nomeMes, dataCurta, rotuloDia, FORMAS, vazio, limpar, efetivar } from './util.js';
import { estado } from './form.js';
import { pagarFatura } from './cartoes.js';
import { definirMesOrcamento } from './orcamento.js';

const GRUPOS = {
  disponivel: ['corrente', 'dinheiro'],
  beneficio: ['beneficio'],
  investimento: ['poupanca', 'investimento'],
  outros: ['terceiros'],
};
// Período do quadro e dos próximos eventos: meses fechados (1 = só este mês, 2 = este e o próximo...). Lembrado neste aparelho.
const OPCOES_MESES = [[1, 'Só este mês'], [2, 'Este mês e o próximo'], [3, 'Este mês e os 2 seguintes'], [6, 'Este mês e os 5 seguintes']];
let meses = (() => { try { const v = +localStorage.getItem('fin-meses-resumo'); return OPCOES_MESES.some(o => o[0] === v) ? v : 1; } catch { return 1; } })();
function fimDoPeriodo(n) {
  const d = new Date(new Date().getFullYear(), new Date().getMonth() + n, 0);   // último dia do mês final
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
let geradoMes = null;
let mesResumo = null;    // mês do quadro "Resumo de ..." (null = mês atual)

// Recorrências geram os previstos sozinhas: o mês atual e os 5 seguintes (idempotente; é uma janela que anda, nunca infinita).
async function gerarRecorrencias() {
  const mes = mesISO();
  if (geradoMes === mes) return;
  geradoMes = mes;
  try { await POST('/api/recorrencias/gerar', { mes, ate: somarMes(mes, 5) }); } catch { geradoMes = null; }
}

export async function inicio(raiz, ctx) {
  const ateISO = fimDoPeriodo(meses);
  const mes = mesISO();
  await gerarRecorrencias();
  try { await POST('/api/investimentos/recalcular'); } catch { /* sem investimentos ou offline: segue */ }   // rendimentos previstos das contas de investimento
  const [sd, resumo, caps, lem] = await Promise.all([GET(`/api/saldo-disponivel?ate=${ateISO}`), GET(`/api/resumo/mensal?mes=${mesResumo || mes}`), GET('/api/capturas'), GET(`/api/lembretes?ate=${ateISO}`)]);
  const contas = sd.contas;
  const soma = (classes, f) => contas.filter(c => classes.includes(c.tipo)).reduce((a, c) => a + f(c), 0);
  const livre = (classes) => soma(classes, c => c.projetado);       // inclui o que ainda vai entrar: assim o Total bate com Saldo + A receber + A pagar + Faturas
  const total = (f) => contas.reduce((a, c) => a + f(c), 0);

  limpar(raiz).append(
    h('h1', null, `Olá, ${estado.eu.nome.split(' ')[0]}`),
    caps.length ? h('a', { class: 'banner', href: '#/capturar' }, `📷 ${caps.length} captura(s) aguardando sua conferência`) : null,
    h('section', { class: 'cartao destaque' },
      h('div', { class: 'linha-controles' },
        h('div', { class: 'rotulo' }, `Posição até ${dataCurta(sd.ate)}`),
        h('select', { 'aria-label': 'Período', value: String(meses), onchange: (e) => { meses = +e.target.value; try { localStorage.setItem('fin-meses-resumo', String(meses)); } catch { /* sem armazenamento */ } inicio(raiz, ctx); } },
          OPCOES_MESES.map(([n, rot]) => h('option', { value: n }, rot)))),
      quadroResumo(livre),
      h('div', { class: 'formula' },
        h('span', null, 'Saldo ', h('b', null, brl(total(c => c.saldo_atual)))),
        h('span', null, 'A receber ', h('b', null, brl(total(c => c.entradas_previstas)))),
        h('span', null, 'A pagar ', h('b', null, brl(total(c => c.saidas_previstas)))),
        h('span', null, 'Faturas ', h('b', null, brl(total(c => c.faturas_total)))))),
    blocoEventos(lem, () => inicio(raiz, ctx)),
    h('h2', null, 'Contas'),
    contas.length ? contas.map(c => cartaoConta(c, estado.eu.id)) : vazio('Nenhuma conta ainda. Vá em Mais › Contas para criar a primeira.'),
    blocoResumoMes(mesResumo || mes, resumo),
    h('a', { class: 'btn sec', href: '#/orcamento', onclick: () => definirMesOrcamento(mesResumo || mes) }, 'Ver orçamento do mês'));
}

// Disponível = saldo + a receber + a pagar + faturas a vencer no período (por grupo de contas): a posição esperada ao fim do período.
function quadroResumo(livre) {
  const d = livre(GRUPOS.disponivel), b = livre(GRUPOS.beneficio), inv = livre(GRUPOS.investimento), o = livre(GRUPOS.outros);
  const sub = d + b;
  const linha = (rot, v, classe, dica) => h('div', { class: 'res-linha ' + (classe || ''), title: dica || null },
    h('span', null, rot), h('b', { class: v < 0 ? 'neg' : '' }, brl(v)));
  return h('div', { class: 'resumo-pos' },
    linha('Disponível', d, '', 'Dinheiro e contas correntes'),
    linha('Benefícios', b, '', 'Ticket / vale'),
    linha('Subtotal', sub, 'sub'),
    linha('Investimento', inv, '', 'Poupança e investimentos'),
    linha('Outros', o, '', 'Terceiros'),
    linha('Total', sub + inv + o, 'total'));
}

function cartaoConta(c, eu) {
  const formas = Object.entries(c.por_forma || {});
  return h('details', { class: 'cartao conta' },
    h('summary', null,
      h('div', null, h('b', null, c.nome), c.dono_id !== eu ? h('small', { class: 'selo' }, `de ${c.dono_nome}`) : null,
        c.tipo_nome ? h('small', { class: 'selo' }, c.tipo_nome) : null),
      h('div', { class: 'valor ' + (c.projetado < 0 ? 'neg' : '') }, brl(c.projetado))),
    h('dl', { class: 'detalhe' },
      h('dt', null, 'Saldo atual'), h('dd', null, brl(c.saldo_atual)),
      formas.map(([f, v]) => [h('dt', null, `A pagar · ${FORMAS[f] || f}`), h('dd', null, brl(v))]),
      c.faturas.map(f => [h('dt', null, `Fatura ${f.cartao_nome} (vence ${dataCurta(f.data_vencimento)})`), h('dd', null, brl(f.total))]),
      c.entradas_previstas ? [h('dt', null, 'A receber'), h('dd', null, brl(c.entradas_previstas))] : null));
}

// "Resumo de <mês>" com setas para navegar entre os meses (só este bloco recarrega)
function blocoResumoMes(mes, inicial) {
  const caixa = h('div');
  const desenhar = (m, dados) => {
    const ehAtual = m === mesISO();
    limpar(caixa).append(
      h('div', { class: 'navmes' }, h('button', { class: 'icone', 'aria-label': 'Mês anterior', onclick: () => ir(m, -1) }, '‹'),
        h('h2', { class: 'resumo-titulo' }, `Resumo de ${nomeMes(m)}`),
        h('button', { class: 'icone', 'aria-label': 'Próximo mês', onclick: () => ir(m, 1) }, '›')),
      ehAtual ? null : h('button', { class: 'btn link', onclick: () => ir(mesISO(), 0) }, 'Voltar para o mês atual'),
      resumoMes(dados));
  };
  const ir = async (m, n) => {
    const novo = somarMes(m, n);
    try {
      const dados = await GET(`/api/resumo/mensal?mes=${novo}`);
      mesResumo = novo === mesISO() ? null : novo;
      desenhar(novo, dados);
    } catch (e) { aviso(e.message || 'Erro ao carregar o mês', true); }
  };
  desenhar(mes, inicial);
  return caixa;
}

function resumoMes(r) {
  const max = Math.max(1, ...r.grupos.map(g => -g.total));
  return h('section', { class: 'cartao' },
    h('div', { class: 'tres' },
      h('div', null, h('small', null, 'Receitas'), h('b', { class: 'pos' }, brl(r.receitas))),
      h('div', null, h('small', null, 'Despesas'), h('b', { class: 'neg' }, brl(r.despesas))),
      h('div', null, h('small', null, 'Resultado'), h('b', { class: r.resultado < 0 ? 'neg' : 'pos' }, brl(r.resultado)))),
    r.grupos.length ? h('div', { class: 'barras' }, r.grupos.slice(0, 8).map(g =>
      h('div', { class: 'barra' }, h('span', null, g.grupo), h('div', { class: 'trilho' }, h('div', { class: 'enchimento', style: `width:${Math.round(-g.total / max * 100)}%` })),
        h('b', null, brl(-g.total))))) : vazio('Sem lançamentos neste mês (competência).'));
}

// estado de recolhimento dos grupos de "Próximos eventos" (mantido enquanto o app está aberto)
const gruposAbertos = new Map();

function blocoEventos(l, recarregar) {
  const dias_ = (iso) => Math.round((new Date(iso + 'T00:00:00') - new Date(l.hoje + 'T00:00:00')) / 864e5);
  const quando = (i) => { const d = dias_(String(i.data).slice(0, 10)); return d < 0 ? `${-d}d atrás` : d === 0 ? 'hoje' : d === 1 ? 'amanhã' : dataCurta(i.data); };

  const linha = (i, mostrarQuando) => {
    const fat = i.tipo === 'fatura', transf = i.tipo === 'transferencia', venc = i.tipo === 'vencimento';
    if (venc) {
      const d = dias_(String(i.data).slice(0, 10));
      return h('div', { class: 'item lembrete ' + (i.atrasado ? 'atrasado' : '') },
        mostrarQuando ? h('div', { class: 'quando' }, quando(i)) : null,
        h('div', { class: 'corpo' }, h('b', null, `Vencimento: ${i.conta_nome}`), h('small', null, d < 0 ? `venceu há ${-d} dia(s) · decida o que fazer com o saldo` : d === 0 ? 'vence hoje' : `vence em ${d} dia(s)`)),
        h('b', { class: 'pos' }, brl(i.valor_centavos)),
        h('a', { class: 'btn mini-btn sec', href: '#/investimentos' }, 'Ver'));
    }
    const titulo = fat ? `Fatura ${i.cartao_nome}` : transf ? 'Transferência' : (i.favorecido_nome || i.descricao || i.categoria_nome || 'Previsto');
    const sub = transf ? [i.origem_nome && i.destino_nome ? `${i.origem_nome} → ${i.destino_nome}` : i.conta_nome, i.descricao].filter(Boolean).join(' · ') : fat ? `vence ${dataCurta(i.data)} · ${i.fechada ? 'fechada' : 'ainda aberta'}${i.alem_periodo ? ' · após o período' : ''}` : [i.conta_nome, i.categoria_nome].filter(Boolean).join(' · ');
    return h('div', { class: 'item lembrete ' + (i.atrasado ? 'atrasado ' : '') + (i.alem_periodo ? 'alem' : '') },
      mostrarQuando ? h('div', { class: 'quando' }, quando(i)) : null,
      h('div', { class: 'corpo' }, h('b', null, titulo), h('small', null, sub)),
      h('b', { class: transf ? '' : i.valor_centavos < 0 ? 'neg' : 'pos' }, brl(i.valor_centavos)),
      fat ? h('button', { class: 'btn mini-btn', onclick: () => pagarFatura({ nome: i.cartao_nome, conta_pagamento_id: i.conta_pagamento_id }, i, recarregar) }, 'Pagar')
          : h('button', { class: 'btn mini-btn sec', onclick: acao(async () => { const r = await efetivar({ id: i.id, titulo, valor_centavos: i.valor_centavos, prevista: i.data, rotulo: transf ? 'Fiz' : i.valor_centavos < 0 ? 'Paguei' : 'Recebi' }); if (!r) return; aviso(r === 'ajustado' ? 'Previsão ajustada' : transf ? 'Transferência confirmada' : 'Confirmado'); recarregar(); }) }, transf ? 'Fiz' : i.valor_centavos < 0 ? 'Paguei' : 'Recebi'));
  };

  // grupos: todos os atrasados juntos, depois um por data
  const grupos = [];
  for (const i of l.itens) {
    const d = String(i.data).slice(0, 10);
    const chave = d < l.hoje ? 'atrasados' : d;
    let g = grupos.find(x => x.chave === chave);
    if (!g) { g = { chave, itens: [] }; grupos.push(g); }
    g.itens.push(i);
  }
  const rotulo = (g) => g.chave === 'atrasados' ? 'Atrasados' : g.chave === l.hoje ? 'Hoje' : dias_(g.chave) === 1 ? `Amanhã · ${dataCurta(g.chave)}` : rotuloDia(g.chave);
  // padrão: atrasados e hoje abertos; se não houver nenhum dos dois, abre só o primeiro grupo
  const abertoPadrao = (g, n) => g.chave === 'atrasados' || g.chave === l.hoje || (n === 0 && !grupos.some(x => x.chave === 'atrasados' || x.chave === l.hoje));
  const aberto = (g, n) => gruposAbertos.has(g.chave) ? gruposAbertos.get(g.chave) : abertoPadrao(g, n);
  const redesenhar = () => { const novo = blocoEventos(l, recarregar); secao.replaceWith(novo); };
  const definirTodos = (v) => { grupos.forEach(g => gruposAbertos.set(g.chave, v)); redesenhar(); };
  const todosAbertos = grupos.every((g, n) => aberto(g, n));

  const secao = h('section', null,
    h('h2', null, 'Próximos eventos'),
    h('small', { class: 'dica' }, `Até ${dataCurta(l.ate)} · a pagar ${brl(-l.saidas)}${l.entradas ? ` · a receber ${brl(l.entradas)}` : ''}`),
    grupos.length > 1 ? h('button', { class: 'btn link', onclick: () => definirTodos(!todosAbertos) }, todosAbertos ? '▲ Recolher tudo' : '▼ Expandir tudo') : null,
    grupos.length ? grupos.map((g, n) => {
      const abre = aberto(g, n);
      const saldo = g.itens.filter(i => i.tipo !== 'transferencia').reduce((a, i) => a + i.valor_centavos, 0);
      return h('div', { class: 'grupo-eventos' },
        h('button', { class: 'grupo-topo' + (g.chave === 'atrasados' ? ' atrasado' : ''), 'aria-expanded': String(abre), onclick: () => { gruposAbertos.set(g.chave, !abre); redesenhar(); } },
          h('span', { class: 'seta' }, abre ? '▾' : '▸'), h('b', null, rotulo(g)), h('small', null, `${g.itens.length} evento${g.itens.length > 1 ? 's' : ''}`),
          h('span', { class: 'grupo-total ' + (saldo < 0 ? 'neg' : saldo > 0 ? 'pos' : '') }, saldo ? brl(saldo) : '')),
        abre ? g.itens.map(i => linha(i, g.chave === 'atrasados')) : null);
    }) : vazio('Nada pendente neste período.'));
  return secao;
}
