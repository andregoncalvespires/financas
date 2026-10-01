import { h, GET, POST, PATCH, brl, aviso, acao, mesISO, somarMes, nomeMes, dataCurta, FORMAS, vazio, limpar, dataEfetivacao } from './util.js';
import { estado } from './form.js';
import { pagarFatura } from './cartoes.js';

const GRUPOS = {
  disponivel: ['corrente', 'dinheiro'],
  beneficio: ['beneficio'],
  investimento: ['poupanca', 'investimento'],
  outros: ['terceiros'],
};
let dias = 30;           // período do resumo e dos próximos eventos
let geradoMes = null;

// Recorrências geram os previstos do mês sozinhas (idempotente): lembretes não dependem de apertar botão.
async function gerarRecorrencias() {
  const mes = mesISO();
  if (geradoMes === mes) return;
  geradoMes = mes;
  try {
    await POST('/api/recorrencias/gerar', { mes });
    if (new Date().getDate() >= 22) await POST('/api/recorrencias/gerar', { mes: somarMes(mes, 1) });
  } catch { geradoMes = null; }
}

export async function inicio(raiz, ctx) {
  const ate = new Date(Date.now() + dias * 864e5);
  const ateISO = `${ate.getFullYear()}-${String(ate.getMonth() + 1).padStart(2, '0')}-${String(ate.getDate()).padStart(2, '0')}`;
  const mes = mesISO();
  await gerarRecorrencias();
  const [sd, resumo, caps, lem] = await Promise.all([GET(`/api/saldo-disponivel?ate=${ateISO}`), GET(`/api/resumo/mensal?mes=${mes}`), GET('/api/capturas'), GET(`/api/lembretes?dias=${dias}`)]);
  const contas = sd.contas;
  const soma = (classes, f) => contas.filter(c => classes.includes(c.tipo)).reduce((a, c) => a + f(c), 0);
  const livre = (classes) => soma(classes, c => c.livre);
  const total = (f) => contas.reduce((a, c) => a + f(c), 0);

  limpar(raiz).append(
    h('h1', null, `Olá, ${estado.eu.nome.split(' ')[0]}`),
    caps.length ? h('a', { class: 'banner', href: '#/capturar' }, `📷 ${caps.length} captura(s) aguardando sua conferência`) : null,
    h('section', { class: 'cartao destaque' },
      h('div', { class: 'linha-controles' },
        h('div', { class: 'rotulo' }, `Posição até ${dataCurta(sd.ate)}`),
        h('select', { 'aria-label': 'Período', value: String(dias), onchange: (e) => { dias = +e.target.value; inicio(raiz, ctx); } },
          [7, 15, 30, 60, 90].map(d => h('option', { value: d }, `próx. ${d} dias`)))),
      quadroResumo(livre),
      h('div', { class: 'formula' },
        h('span', null, 'Saldo ', h('b', null, brl(total(c => c.saldo_atual)))),
        h('span', null, 'A receber ', h('b', null, brl(total(c => c.entradas_previstas)))),
        h('span', null, 'A pagar ', h('b', null, brl(total(c => c.saidas_previstas)))),
        h('span', null, 'Faturas ', h('b', null, brl(total(c => c.faturas_total)))))),
    blocoEventos(lem, () => inicio(raiz, ctx)),
    h('h2', null, 'Contas'),
    contas.length ? contas.map(c => cartaoConta(c, estado.eu.id)) : vazio('Nenhuma conta ainda. Vá em Mais › Contas para criar a primeira.'),
    h('h2', null, `Resumo de ${nomeMes(mes)}`),
    resumoMes(resumo),
    h('a', { class: 'btn sec', href: '#/orcamento' }, 'Ver orçamento do mês'));
}

// Disponível = saldo + saídas previstas + faturas a vencer no período (por grupo de contas).
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
      h('div', { class: 'valor ' + (c.livre < 0 ? 'neg' : '') }, brl(c.livre))),
    h('dl', { class: 'detalhe' },
      h('dt', null, 'Saldo atual'), h('dd', null, brl(c.saldo_atual)),
      formas.map(([f, v]) => [h('dt', null, `A pagar · ${FORMAS[f] || f}`), h('dd', null, brl(v))]),
      c.faturas.map(f => [h('dt', null, `Fatura ${f.cartao_nome} (vence ${dataCurta(f.data_vencimento)})`), h('dd', null, brl(f.total))]),
      c.entradas_previstas ? [h('dt', null, 'A receber'), h('dd', null, brl(c.entradas_previstas))] : null));
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

function blocoEventos(l, recarregar) {
  const dias_ = (iso) => Math.round((new Date(iso + 'T00:00:00') - new Date(l.hoje + 'T00:00:00')) / 864e5);
  const quando = (i) => { const d = dias_(String(i.data).slice(0, 10)); return d < 0 ? `${-d}d atrás` : d === 0 ? 'hoje' : d === 1 ? 'amanhã' : dataCurta(i.data); };
  return h('section', null,
    h('h2', null, 'Próximos eventos'),
    h('small', { class: 'dica' }, `Até ${dataCurta(l.ate)} · a pagar ${brl(-l.saidas)}${l.entradas ? ` · a receber ${brl(l.entradas)}` : ''}`),
    l.itens.length ? l.itens.map(i => {
      const fat = i.tipo === 'fatura', transf = i.tipo === 'transferencia';
      const titulo = fat ? `Fatura ${i.cartao_nome}` : transf ? 'Transferência' : (i.favorecido_nome || i.descricao || i.categoria_nome || 'Previsto');
      const sub = transf ? [i.origem_nome && i.destino_nome ? `${i.origem_nome} → ${i.destino_nome}` : i.conta_nome, i.descricao].filter(Boolean).join(' · ') : fat ? `vence ${dataCurta(i.data)} · ${i.fechada ? 'fechada' : 'ainda aberta'}${i.alem_periodo ? ' · após o período' : ''}` : [i.conta_nome, i.categoria_nome].filter(Boolean).join(' · ');
      return h('div', { class: 'item lembrete ' + (i.atrasado ? 'atrasado ' : '') + (i.alem_periodo ? 'alem' : '') },
        h('div', { class: 'quando' }, quando(i)),
        h('div', { class: 'corpo' }, h('b', null, titulo), h('small', null, sub)),
        h('b', { class: transf ? '' : i.valor_centavos < 0 ? 'neg' : 'pos' }, brl(i.valor_centavos)),
        fat ? h('button', { class: 'btn mini-btn', onclick: () => pagarFatura({ nome: i.cartao_nome, conta_pagamento_id: i.conta_pagamento_id }, i, recarregar) }, 'Pagar')
            : h('button', { class: 'btn mini-btn sec', onclick: acao(async () => { const dia = await dataEfetivacao({ titulo, valor: brl(i.valor_centavos), prevista: i.data, rotulo: transf ? 'Fiz' : i.valor_centavos < 0 ? 'Paguei' : 'Recebi' }); if (!dia) return; await POST(`/api/transacoes/${i.id}/confirmar`, { data_caixa: dia }); aviso(transf ? 'Transferência confirmada' : 'Confirmado'); recarregar(); }) }, transf ? 'Fiz' : i.valor_centavos < 0 ? 'Paguei' : 'Recebi'));
    }) : vazio(`Nada pendente nos próximos ${dias} dias.`));
}
