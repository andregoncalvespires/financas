import { h, GET, POST, campo, brl, hojeISO, folha, aviso, acao, limpar, vazio, mesISO, somarMes, intervaloMes, nomeMes, rotuloDia, FORMAS, dataLonga, confirmar, efetivar } from './util.js';
import { formTransacao, excluirTransacao, estado } from './form.js';

const filtro = { mes: mesISO(), base: 'competencia', soPrevistos: false };

export async function lancamentos(raiz, ctx) {
  const [de, ate] = intervaloMes(filtro.mes);
  const q = `de=${de}&ate=${ate}&base=${filtro.base}&limite=1000${filtro.soPrevistos ? '&estado=previsto' : ''}`;
  const rows = await GET(`/api/transacoes?${q}`);
  const col = filtro.base === 'competencia' ? 'data_competencia' : 'data_caixa';
  const rec = rows.filter(t => t.tipo === 'receita').reduce((a, t) => a + t.valor_centavos, 0);
  const desp = rows.filter(t => t.tipo === 'despesa').reduce((a, t) => a + t.valor_centavos, 0);
  const ir = (n) => { filtro.mes = somarMes(filtro.mes, n); lancamentos(raiz, ctx); };

  const dias = new Map();
  for (const t of rows) { const d = String(t[col]).slice(0, 10); if (!dias.has(d)) dias.set(d, []); dias.get(d).push(t); }

  limpar(raiz).append(
    h('h1', null, 'Lançamentos'),
    h('div', { class: 'navmes' }, h('button', { class: 'icone', 'aria-label': 'Mês anterior', onclick: () => ir(-1) }, '‹'),
      h('b', null, nomeMes(filtro.mes)), h('button', { class: 'icone', 'aria-label': 'Próximo mês', onclick: () => ir(1) }, '›')),
    h('div', { class: 'linha-controles' },
      h('div', { class: 'segmentado' },
        h('button', { class: 'seg ' + (filtro.base === 'competencia' ? 'ativo' : ''), onclick: () => { filtro.base = 'competencia'; lancamentos(raiz, ctx); } }, 'Competência'),
        h('button', { class: 'seg ' + (filtro.base === 'caixa' ? 'ativo' : ''), onclick: () => { filtro.base = 'caixa'; lancamentos(raiz, ctx); } }, 'Caixa')),
      h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: filtro.soPrevistos, onchange: (e) => { filtro.soPrevistos = e.target.checked; lancamentos(raiz, ctx); } }), h('span', null, 'Só previstos'))),
    h('div', { class: 'tres cartao' },
      h('div', null, h('small', null, 'Receitas'), h('b', { class: 'pos' }, brl(rec))),
      h('div', null, h('small', null, 'Despesas'), h('b', { class: 'neg' }, brl(desp))),
      h('div', null, h('small', null, 'Resultado'), h('b', { class: rec + desp < 0 ? 'neg' : 'pos' }, brl(rec + desp)))),
    rows.length ? [...dias.entries()].map(([d, ts]) => h('section', null, h('h3', { class: 'dia' }, rotuloDia(d)), ts.map(t => linha(t, raiz, ctx)))) : vazio('Nenhum lançamento neste período.'),
    h('button', { class: 'btn link', onclick: () => exportar() }, '⬇ Exportar para Excel'),
    h('a', { class: 'fab', href: '#/novo', 'aria-label': 'Novo lançamento' }, '+'));
}

function linha(t, raiz, ctx) {
  const onde = t.plastico_id ? `${t.cartao_nome} ·· ${t.plastico_final}` : t.conta_nome;
  const transf = t.tipo === 'transferencia';
  const titulo = transf ? `Transferência ${t.contraparte_nome ? (t.valor_centavos < 0 ? 'para ' : 'de ') + t.contraparte_nome : ''}`.trim()
    : (t.favorecido_nome || t.descricao || (t.tipo === 'pagamento_fatura' ? 'Pagamento de fatura' : 'Sem descrição'));
  const sub = [transf ? t.descricao : t.categoria_nome, onde, t.total_parcelas ? `${t.numero_parcela}/${t.total_parcelas}` : null, t.criado_por !== estado.eu.id ? `por ${t.criado_por_nome}` : null].filter(Boolean).join(' · ');
  return h('button', { class: 'linha item', onclick: () => detalhe(t, () => lancamentos(raiz, ctx)) },
    h('div', { class: 'corpo' }, h('b', null, titulo, t.estado === 'previsto' ? h('small', { class: 'selo aviso' }, 'previsto') : null), h('small', null, sub)),
    h('b', { class: t.valor_centavos < 0 ? 'neg' : 'pos' }, brl(t.valor_centavos)));
}

export function detalhe(t, recarregar) {
  folha('Lançamento', (corpo, fechar) => {
    const editavel = t.tipo === 'despesa' || t.tipo === 'receita';
    corpo.append(h('p', { class: 'dica' }, `Competência ${dataLonga(t.data_competencia)} · caixa ${dataLonga(t.data_caixa)}${t.forma_pagamento ? ' · ' + (FORMAS[t.forma_pagamento] || t.forma_pagamento) : ''}`));
    if (t.anexo_id) corpo.append(h('a', { href: `/api/anexos/${t.anexo_id}`, target: '_blank', rel: 'noopener' }, h('img', { class: 'comprovante', src: `/api/anexos/${t.anexo_id}`, alt: 'Comprovante' })));
    if (t.tipo === 'transferencia') corpo.append(h('p', null, t.contraparte_nome
      ? (t.valor_centavos < 0 ? `De ${t.conta_nome} para ${t.contraparte_nome}` : `De ${t.contraparte_nome} para ${t.conta_nome}`) : `Transferência ${t.valor_centavos < 0 ? 'saindo de' : 'entrando em'} ${t.conta_nome}`),
      t.descricao ? h('p', { class: 'dica' }, t.descricao) : null, h('p', { class: 'dica' }, 'Não conta como receita nem despesa. Confirmar ou excluir vale para as duas pontas.'));
    if (t.estado === 'previsto') corpo.append(h('button', { class: 'btn', onclick: acao(async () => {
      let r = 'confirmado';
      if (t.plastico_id) await POST(`/api/transacoes/${t.id}/confirmar`);      // compra no cartão segue a fatura: sem valor/data
      else { r = await efetivar({ id: t.id, titulo: t.favorecido_nome || t.descricao || t.categoria_nome || 'Lançamento', valor_centavos: t.valor_centavos, prevista: t.data_caixa }); if (!r) return; }
      fechar(); aviso(r === 'ajustado' ? 'Previsão ajustada' : 'Confirmado'); recarregar(); }) }, '✔ Confirmar que aconteceu'));
    if ((t.estado === 'confirmado') && !t.plastico_id && t.tipo !== 'pagamento_fatura') corpo.append(h('button', { class: 'btn link', onclick: acao(async () => {
      if (!(await confirmar(t.transferencia_id ? 'Voltar esta transferência para previsto? As duas contas serão ajustadas.' : 'Voltar este lançamento para previsto? O saldo da conta será ajustado.', 'Voltar para previsto'))) return;
      await POST(`/api/transacoes/${t.id}/desfazer`); fechar(); aviso('Voltou para previsto'); recarregar(); }) }, '↩ Voltar para previsto'));
    if (editavel) corpo.append(formTransacao({ editar: t, inicial: { tipo: t.tipo, valor_centavos: t.valor_centavos, data_competencia: t.data_competencia, descricao: t.descricao,
      favorecido_nome: t.favorecido_nome, categoria_id: t.categoria_id, forma_pagamento: t.forma_pagamento, estado: t.estado },
      aoSalvar: async () => { fechar(); recarregar(); }, aoCancelar: fechar }));
    corpo.append(h('button', { class: 'btn link perigo', onclick: acao(async () => { if (await excluirTransacao(t)) { fechar(); recarregar(); } }) }, 'Excluir'));
  });
}

export async function novo(raiz, ctx) {
  limpar(raiz).append(h('h1', null, 'Novo lançamento'),
    h('section', { class: 'cartao' }, formTransacao({ aoSalvar: async () => { location.hash = '#/lancamentos'; }, aoCancelar: () => history.back() })));
}

function exportar() {
  const [de0, ate0] = intervaloMes(filtro.mes);
  folha('Exportar para Excel', (corpo, fechar) => {
    const de = h('input', { type: 'date', value: de0 }), ate = h('input', { type: 'date', value: ate0 });
    const base = h('select', { value: filtro.base }, h('option', { value: 'competencia' }, 'Competência'), h('option', { value: 'caixa' }, 'Caixa'));
    corpo.append(h('p', { class: 'dica' }, 'Gera uma planilha com três abas: Lançamentos, Faturas e Itens das faturas. Inclui só o que você tem permissão de ver.'),
      campo('De', de), campo('Até', ate), campo('Período por data de', base),
      h('button', { class: 'btn', onclick: () => {
        if (!de.value || !ate.value || ate.value < de.value) return aviso('Confira o período.', true);
        window.location.href = `/api/exportar?de=${de.value}&ate=${ate.value}&base=${base.value}`;
        fechar();
      } }, 'Baixar planilha'));
  });
}
