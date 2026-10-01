import { h, GET, POST, api, campo, campoFavorecido, brl, hojeISO, folha, aviso, acao, limpar, vazio, mesISO, somarMes, intervaloMes, nomeMes, rotuloDia, FORMAS, dataLonga, confirmar, efetivar } from './util.js';
import { formTransacao, excluirTransacao, estado } from './form.js';

const vazioF = () => ({ modo: 'mes', de: '', ate: '', base: 'competencia', estado: '', tipo: '', conta: '', cartao: '', plastico: '', fatura: '',
  favorecido: null, categoria: '', busca: '' });
const filtro = { mes: mesISO(), ...vazioF(), detalhe: false };
const selecao = { ativa: false, ids: new Set() };   // modo de seleção para excluir vários lançamentos

// parâmetros da API a partir do filtro (a mesma consulta alimenta a lista, os totais e o detalhamento)
function parametros() {
  const [de, ate] = filtro.modo === 'intervalo' && filtro.de && filtro.ate ? [filtro.de, filtro.ate] : intervaloMes(filtro.mes);
  const p = new URLSearchParams({ de, ate, base: filtro.base });
  const mapa = { estado: filtro.estado, tipo: filtro.tipo, conta_id: filtro.conta, cartao_id: filtro.cartao, plastico_id: filtro.plastico, fatura_id: filtro.fatura,
    favorecido_id: filtro.favorecido && filtro.favorecido.id, categoria_id: filtro.categoria, busca: filtro.busca.trim() };
  for (const [k, v] of Object.entries(mapa)) if (v) p.set(k, v);
  return p;
}

const temFiltro = () => !!(filtro.estado || filtro.tipo || filtro.conta || filtro.cartao || filtro.plastico || filtro.fatura || filtro.favorecido || filtro.categoria || filtro.busca.trim() || filtro.modo === 'intervalo');

export async function lancamentos(raiz, ctx) {
  const p = parametros();
  const [rows, tot, nomes] = await Promise.all([
    GET(`/api/transacoes?${p}&limite=1000`), GET(`/api/transacoes/resumo?${p}`), nomesFiltro()]);
  const col = filtro.base === 'competencia' ? 'data_competencia' : 'data_caixa';
  const rec = tot.receitas, desp = tot.despesas;
  const recarregar = () => lancamentos(raiz, ctx);
  const ir = (n) => { filtro.mes = somarMes(filtro.mes, n); recarregar(); };

  const dias = new Map();
  for (const t of rows) { const d = String(t[col]).slice(0, 10); if (!dias.has(d)) dias.set(d, []); dias.get(d).push(t); }

  // chips dos filtros ativos (cada um se remove com ×)
  const chips = [];
  const chip = (texto, limpar) => chips.push(h('button', { class: 'chip', onclick: () => { limpar(); recarregar(); }, 'aria-label': `Remover filtro ${texto}` }, texto, h('span', null, ' ✕')));
  if (filtro.modo === 'intervalo') chip(`${dataLonga(filtro.de)} a ${dataLonga(filtro.ate)}`, () => { filtro.modo = 'mes'; filtro.de = filtro.ate = ''; });
  if (filtro.conta) chip(nomes.conta(filtro.conta), () => { filtro.conta = ''; });
  if (filtro.cartao) chip(nomes.cartao(filtro.cartao), () => { filtro.cartao = filtro.plastico = filtro.fatura = ''; });
  if (filtro.plastico) chip(nomes.plastico(filtro.plastico), () => { filtro.plastico = ''; });
  if (filtro.fatura) chip('Fatura selecionada', () => { filtro.fatura = ''; });
  if (filtro.favorecido) chip(filtro.favorecido.nome, () => { filtro.favorecido = null; });
  if (filtro.categoria) chip(nomes.categoria(filtro.categoria), () => { filtro.categoria = ''; });
  if (filtro.tipo) chip({ despesa: 'Despesas', receita: 'Receitas', transferencia: 'Transferências', pagamento_fatura: 'Pagamentos de fatura' }[filtro.tipo], () => { filtro.tipo = ''; });
  if (filtro.estado) chip(filtro.estado === 'previsto' ? 'Só previstos' : 'Só confirmados', () => { filtro.estado = ''; });
  if (filtro.busca.trim()) chip(`“${filtro.busca.trim()}”`, () => { filtro.busca = ''; });

  const bloco = (titulo, itens, aplicar) => h('div', { class: 'quebra' }, h('h3', null, titulo),
    itens.length ? itens.slice(0, 10).map(i => h(i.id ? 'button' : 'div', { class: 'linha item', onclick: i.id ? () => { aplicar(i); recarregar(); } : null },
      h('div', { class: 'corpo' }, h('b', null, i.nome), h('small', null, `${i.itens} lançamento${i.itens > 1 ? 's' : ''}`)),
      h('b', { class: i.total < 0 ? 'neg' : 'pos' }, brl(i.total)))) : vazio('Nada para mostrar.'));

  // barra de ações da seleção: marcar todas, limpar e excluir
  const total = rows.length;
  const info = h('b');
  const barra = h('div', { class: 'imp-rodape barra-selecao' }, info,
    h('button', { class: 'btn sec mini-btn', onclick: () => { for (const t of rows) selecao.ids.add(t.id); document.querySelectorAll('.sel-caixa').forEach(c => { c.checked = true; }); atualizarBarra(); } }, `Marcar todas (${total})`),
    h('button', { class: 'btn sec mini-btn', onclick: () => { selecao.ids.clear(); document.querySelectorAll('.sel-caixa').forEach(c => { c.checked = false; }); atualizarBarra(); } }, 'Limpar'),
    h('button', { class: 'btn perigo mini-btn', id: 'sel-excluir', onclick: () => excluirMarcadas(rows, recarregar) }, 'Excluir marcadas'));
  function atualizarBarra() {
    info.textContent = `${selecao.ids.size} marcada(s)`;
    const b = barra.querySelector('#sel-excluir'); if (b) b.disabled = !selecao.ids.size;
  }
  limpar(raiz).append(
    h('h1', null, 'Lançamentos'),
    filtro.modo === 'intervalo' ? null : h('div', { class: 'navmes' }, h('button', { class: 'icone', 'aria-label': 'Mês anterior', onclick: () => ir(-1) }, '‹'),
      h('b', null, nomeMes(filtro.mes)), h('button', { class: 'icone', 'aria-label': 'Próximo mês', onclick: () => ir(1) }, '›')),
    h('div', { class: 'linha-controles' },
      h('div', { class: 'segmentado' },
        h('button', { class: 'seg ' + (filtro.base === 'competencia' ? 'ativo' : ''), onclick: () => { filtro.base = 'competencia'; recarregar(); } }, 'Competência'),
        h('button', { class: 'seg ' + (filtro.base === 'caixa' ? 'ativo' : ''), onclick: () => { filtro.base = 'caixa'; recarregar(); } }, 'Caixa')),
      h('button', { class: 'btn mini-btn ' + (temFiltro() ? '' : 'sec'), onclick: () => abrirFiltros(recarregar) }, `⚲ Filtros${chips.length ? ` (${chips.length})` : ''}`),
      rows.length ? h('button', { class: 'btn mini-btn ' + (selecao.ativa ? '' : 'sec'), onclick: () => { selecao.ativa = !selecao.ativa; selecao.ids.clear(); recarregar(); } }, selecao.ativa ? '✕ Cancelar seleção' : '☑ Selecionar') : null),
    chips.length ? h('div', { class: 'chips' }, chips, h('button', { class: 'chip limpar', onclick: () => { Object.assign(filtro, vazioF()); recarregar(); } }, 'Limpar tudo')) : null,
    h('div', { class: 'tres cartao' },
      h('div', null, h('small', null, 'Receitas'), h('b', { class: 'pos' }, brl(rec))),
      h('div', null, h('small', null, 'Despesas'), h('b', { class: 'neg' }, brl(desp))),
      h('div', null, h('small', null, 'Resultado'), h('b', { class: rec + desp < 0 ? 'neg' : 'pos' }, brl(rec + desp)))),
    tot.quantidade ? h('button', { class: 'btn link', onclick: () => { filtro.detalhe = !filtro.detalhe; recarregar(); } }, filtro.detalhe ? '▲ Ocultar detalhamento' : '▼ Ver por categoria e favorecido') : null,
    filtro.detalhe ? h('section', { class: 'cartao' }, h('small', { class: 'dica' }, 'Toque em um item para filtrar por ele.'),
      bloco('Por categoria', tot.por_categoria, (i) => { filtro.categoria = i.id; }),
      bloco('Por favorecido', tot.por_favorecido, (i) => { filtro.favorecido = { id: i.id, nome: i.nome }; })) : null,
    rows.length >= 1000 ? h('p', { class: 'dica' }, 'Mostrando os 1000 lançamentos mais recentes da seleção. Os totais acima consideram todos. Use filtros para refinar.') : null,
    rows.length ? [...dias.entries()].map(([d, ts]) => h('section', null, h('h3', { class: 'dia' }, rotuloDia(d)), ts.map(t => linha(t, raiz, ctx, atualizarBarra)))) : vazio('Nenhum lançamento com esses filtros.'),
    h('button', { class: 'btn link', onclick: () => exportar() }, '⬇ Exportar para Excel'),
    selecao.ativa ? barra : h('a', { class: 'fab', href: '#/novo', 'aria-label': 'Novo lançamento' }, '+'));
  atualizarBarra();
}

// nomes para os chips (contas, cartões, plásticos e categorias já carregados uma vez)
let cacheNomes = null;
async function nomesFiltro(forcar = false) {
  if (!cacheNomes || forcar) {
    const [contas, cartoes, cats] = await Promise.all([GET('/api/contas'), GET('/api/cartoes'), GET('/api/categorias')]);
    cacheNomes = { contas, cartoes, cats };
  }
  const { contas, cartoes, cats } = cacheNomes;
  const plasticos = cartoes.flatMap(k => k.plasticos.map(p => ({ ...p, cartao: k.nome })));
  return {
    contas, cartoes, cats,
    conta: (id) => (contas.find(c => c.id === id) || {}).nome || 'Conta',
    cartao: (id) => (cartoes.find(c => c.id === id) || {}).nome || 'Cartão',
    plastico: (id) => { const p = plasticos.find(x => x.id === id); return p ? `${p.cartao} ·· ${p.final || p.rotulo}` : 'Plástico'; },
    categoria: (id) => (cats.find(c => c.id === id) || {}).nome || 'Categoria',
  };
}

const sel = (opcoes, valor, aoMudar) => {
  const s = h('select', { onchange: (e) => aoMudar(e.target.value) });
  for (const o of opcoes) {
    if (o.grupo) { const g = h('optgroup', { label: o.grupo }); for (const x of o.itens) g.append(h('option', { value: x.v, selected: x.v === valor }, x.t)); s.append(g); }
    else s.append(h('option', { value: o.v, selected: o.v === valor }, o.t));
  }
  return s;
};

async function abrirFiltros(aplicar) {
  const n = await nomesFiltro(true);
  const f = { ...filtro, favorecido: filtro.favorecido ? { ...filtro.favorecido } : null };
  folha('Filtros', (corpo, fechar) => {
    const ondeBox = h('div'), periodoBox = h('div');
    // período: mês (setas) ou intervalo livre
    const desenharPeriodo = () => {
      limpar(periodoBox);
      const de = h('input', { type: 'date', value: f.de || intervaloMes(filtro.mes)[0], onchange: (e) => { f.de = e.target.value; } });
      const ate = h('input', { type: 'date', value: f.ate || intervaloMes(filtro.mes)[1], onchange: (e) => { f.ate = e.target.value; } });
      if (f.modo === 'intervalo') { f.de = de.value; f.ate = ate.value; }
      periodoBox.append(h('div', { class: 'segmentado' },
        h('button', { class: 'seg ' + (f.modo === 'mes' ? 'ativo' : ''), type: 'button', onclick: () => { f.modo = 'mes'; desenharPeriodo(); } }, 'Mês'),
        h('button', { class: 'seg ' + (f.modo === 'intervalo' ? 'ativo' : ''), type: 'button', onclick: () => { f.modo = 'intervalo'; desenharPeriodo(); } }, 'Intervalo')),
        f.modo === 'intervalo' ? h('div', { class: 'duas' }, campo('De', de), campo('Até', ate)) : h('small', { class: 'dica' }, `Mês de ${nomeMes(filtro.mes)} (use as setas da tela para trocar).`));
    };
    desenharPeriodo();

    // conta ou cartão; ao escolher um cartão aparecem plástico e fatura
    const desenharOnde = async () => {
      limpar(ondeBox);
      const valor = f.conta ? 'c:' + f.conta : f.cartao ? 'k:' + f.cartao : '';
      ondeBox.append(campo('Conta ou cartão', sel([{ v: '', t: 'Todas' },
        { grupo: 'Contas', itens: n.contas.map(c => ({ v: 'c:' + c.id, t: c.nome })) },
        { grupo: 'Cartões', itens: n.cartoes.map(k => ({ v: 'k:' + k.id, t: k.nome })) }].filter(o => !o.grupo || o.itens.length), valor, (v) => {
        f.conta = v.startsWith('c:') ? v.slice(2) : ''; f.cartao = v.startsWith('k:') ? v.slice(2) : ''; f.plastico = f.fatura = ''; desenharOnde(); })));
      const k = n.cartoes.find(x => x.id === f.cartao);
      if (!k) return;
      if (k.plasticos.length > 1) ondeBox.append(campo('Plástico / portador', sel([{ v: '', t: 'Todos' }, ...k.plasticos.map(p => ({ v: p.id, t: `${p.rotulo || 'Plástico'}${p.final ? ' ·· ' + p.final : ''}${p.portador_nome ? ' · ' + p.portador_nome : ''}` }))], f.plastico, (v) => { f.plastico = v; })));
      try {
        const fats = await GET(`/api/cartoes/${k.id}/faturas`);
        ondeBox.append(campo('Fatura', sel([{ v: '', t: 'Todas' }, ...fats.map(x => ({ v: x.id, t: `Vence ${dataLonga(x.data_vencimento)} · ${x.status}` }))], f.fatura, (v) => { f.fatura = v; })));
      } catch { /* portador sem acesso às faturas: segue só com cartão e plástico */ }
    };
    desenharOnde();

    // favorecido: sugestões dos já cadastrados; só vale o nome escolhido da lista (vazio = todos)
    const campoFav = campoFavorecido({ valor: f.favorecido ? f.favorecido.nome : '', placeholder: 'Todos', aoEscolher: (r) => { f.favorecido = { id: r.id, nome: r.nome }; } });
    campoFav.input.addEventListener('input', () => { if (!f.favorecido || f.favorecido.nome.toLowerCase() !== campoFav.input.value.trim().toLowerCase()) f.favorecido = null; });

    const raizes = n.cats.filter(c => c.ativa && !c.pai_id);
    const opcoesCat = [{ v: '', t: 'Todas' }];
    for (const r of raizes) { opcoesCat.push({ v: r.id, t: `${r.nome} (${r.tipo})` }); for (const s of n.cats.filter(c => c.ativa && c.pai_id === r.id)) opcoesCat.push({ v: s.id, t: `   ${s.nome}` }); }

    const busca = h('input', { type: 'search', placeholder: 'Descrição, favorecido ou categoria', value: f.busca, oninput: (e) => { f.busca = e.target.value; } });
    corpo.append(
      h('h3', null, 'Período'), periodoBox,
      campo('Datas por', sel([{ v: 'competencia', t: 'Competência' }, { v: 'caixa', t: 'Caixa' }], f.base, (v) => { f.base = v; })),
      ondeBox,
      campo('Favorecido', campoFav.el, 'Toque em uma sugestão para filtrar por esse favorecido.'),
      campo('Categoria', sel(opcoesCat, f.categoria, (v) => { f.categoria = v; }), 'Escolher uma categoria principal inclui as subcategorias.'),
      campo('Tipo', sel([{ v: '', t: 'Todos' }, { v: 'despesa', t: 'Despesas' }, { v: 'receita', t: 'Receitas' }, { v: 'transferencia', t: 'Transferências' }, { v: 'pagamento_fatura', t: 'Pagamentos de fatura' }], f.tipo, (v) => { f.tipo = v; })),
      campo('Situação', sel([{ v: '', t: 'Todas' }, { v: 'previsto', t: 'Só previstos' }, { v: 'confirmado', t: 'Só confirmados' }], f.estado, (v) => { f.estado = v; })),
      campo('Buscar por texto', busca),
      h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn sec', type: 'button', onclick: () => { Object.assign(filtro, vazioF()); fechar(); aplicar(); } }, 'Limpar'),
        h('button', { class: 'btn', type: 'button', onclick: () => {
          if (f.modo === 'intervalo' && (!f.de || !f.ate || f.de > f.ate)) { aviso('Informe um período válido (a data inicial não pode passar da final).', true); return; }
          Object.assign(filtro, f); fechar(); aplicar(); } }, 'Aplicar')));
  });
}

function linha(t, raiz, ctx, aoMarcar) {
  const onde = t.plastico_id ? `${t.cartao_nome} ·· ${t.plastico_final}` : t.conta_nome;
  const transf = t.tipo === 'transferencia';
  const titulo = transf ? `Transferência ${t.contraparte_nome ? (t.valor_centavos < 0 ? 'para ' : 'de ') + t.contraparte_nome : ''}`.trim()
    : (t.favorecido_nome || t.descricao || (t.tipo === 'pagamento_fatura' ? 'Pagamento de fatura' : 'Sem descrição'));
  const sub = [transf ? t.descricao : t.categoria_nome, onde, t.total_parcelas ? `${t.numero_parcela}/${t.total_parcelas}` : null, t.criado_por !== estado.eu.id ? `por ${t.criado_por_nome}` : null].filter(Boolean).join(' · ');
  if (selecao.ativa) {
    const caixa = h('input', { type: 'checkbox', class: 'sel-caixa', 'aria-label': `Marcar ${titulo}`, onchange: () => { if (caixa.checked) selecao.ids.add(t.id); else selecao.ids.delete(t.id); aoMarcar(); } });
    caixa.checked = selecao.ids.has(t.id);
    return h('label', { class: 'linha item sel-linha' }, caixa,
      h('div', { class: 'corpo' }, h('b', null, titulo, t.estado === 'previsto' ? h('small', { class: 'selo aviso' }, 'previsto') : null), h('small', null, sub)),
      h('b', { class: t.valor_centavos < 0 ? 'neg' : 'pos' }, brl(t.valor_centavos)));
  }
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
  const [de0, ate0] = filtro.modo === 'intervalo' && filtro.de && filtro.ate ? [filtro.de, filtro.ate] : intervaloMes(filtro.mes);
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

function excluirMarcadas(rows, recarregar) {
  const marcadas = rows.filter(t => selecao.ids.has(t.id));
  if (!marcadas.length) return;
  const parceladas = marcadas.filter(t => t.total_parcelas).length;
  const recorrentes = marcadas.filter(t => t.recorrencia_id).length;
  folha('Excluir lançamentos', (corpo, fechar) => {
    const todo = h('input', { type: 'checkbox' });
    todo.checked = false;
    corpo.append(
      h('p', null, `Você marcou ${marcadas.length} lançamento(s). A exclusão não pode ser desfeita.`),
      parceladas ? h('label', { class: 'imp-futuras' }, todo, h('span', null, `${parceladas} marcado(s) são parcelas: excluir também as demais parcelas (inclusive as futuras) desses parcelamentos`)) : null,
      recorrentes ? h('p', { class: 'dica' }, `${recorrentes} vieram de recorrência: aquele mês fica pulado e não será recriado.`) : null,
      h('p', { class: 'dica' }, 'Lançamentos conciliados, ou que você não tem permissão para excluir, ficam de fora e são avisados no fim.'),
      h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn sec', onclick: fechar }, 'Cancelar'),
        h('button', { class: 'btn perigo', onclick: acao(async () => {
          const r = await api('POST', '/api/transacoes/excluir-lote', { ids: marcadas.map(t => t.id), todo_parcelamento: todo.checked });
          fechar();
          selecao.ids.clear(); selecao.ativa = false;
          aviso(r.falhas.length ? `${r.excluidos} excluído(s); ${r.falhas.length} não puderam ser excluídos (${[...new Set(r.falhas.map(f => f.motivo))].join('; ')})` : `${r.excluidos} lançamento(s) excluído(s)`, r.falhas.length > 0);
          recarregar();
        }) }, `Excluir ${marcadas.length}`)));
  });
}
