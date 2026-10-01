// Cadastros em cache e formulário de lançamento (manual, sugestão da IA e edição).
import { h, GET, POST, PATCH, DEL, api, aviso, acao, campo, campoFavorecido, brl, parseValor, centavosParaCampo, hojeISO, FORMAS, confirmar, folha } from './util.js';

export const estado = { eu: null, contas: [], cartoes: [], categorias: [] };

export async function carregarCadastros() {
  const [contas, cartoes, categorias] = await Promise.all([GET('/api/contas'), GET('/api/cartoes'), GET('/api/categorias')]);
  Object.assign(estado, { contas, cartoes, categorias });
}

// Destinos possíveis para um lançamento: contas em que posso lançar e plásticos que posso usar.
export function destinos() {
  const eu = estado.eu.id;
  const lista = [];
  for (const c of estado.contas) {
    if (c.inativa || c.papel === 'leitor') continue;
    lista.push({ valor: `conta:${c.id}`, rotulo: c.nome + (c.dono_id !== eu ? ` (de ${c.dono_nome})` : ''), dono: c.dono_id, tipo: 'conta', id: c.id });
  }
  for (const k of estado.cartoes) {
    if (k.inativo) continue;
    for (const p of k.plasticos) {
      if (!p.ativo || !(k.sou_dono || p.portador_id === eu)) continue;
      lista.push({ valor: `plastico:${p.id}`, rotulo: `${k.nome} ·· ${p.final}${p.tipo === 'virtual' ? ' virtual' : ''}${p.rotulo && p.rotulo !== 'Principal' ? ' (' + p.rotulo + ')' : ''}${k.sou_dono ? '' : ` (de ${k.dono_nome})`}`,
        dono: k.dono_id, tipo: 'plastico', id: p.id });
    }
  }
  return lista;
}

export function opcoesCategoria(dono, tipo) {
  const cats = estado.categorias.filter(c => c.dono_id === dono && c.ativa && c.tipo === tipo);
  const grupos = cats.filter(c => !c.pai_id);
  return grupos.map(g => {
    const filhos = cats.filter(c => c.pai_id === g.id);
    return h('optgroup', { label: g.nome }, filhos.map(f => h('option', { value: f.id }, f.nome)));
  }).filter(g => g.children.length);
}

/**
 * opts: { inicial, capturaId, anexoId, editar: transação existente, aoSalvar(), aoCancelar() }
 * inicial: { tipo, valor_centavos, data_competencia, descricao, favorecido_nome, categoria_id, conta_id, plastico_id, forma_pagamento, parcelas, estado }
 */
export function formTransacao(opts) {
  const ini = opts.inicial || {};
  const ed = opts.editar || null;
  const dests = destinos();
  const inicialDest = ini.plastico_id ? `plastico:${ini.plastico_id}` : ini.conta_id ? `conta:${ini.conta_id}` : (dests[0] ? dests[0].valor : '');

  let tipo = ini.tipo || 'despesa';
  const btnDesp = h('button', { type: 'button', class: 'seg', onclick: () => setTipo('despesa') }, 'Despesa');
  const btnRec = h('button', { type: 'button', class: 'seg', onclick: () => setTipo('receita') }, 'Receita');
  const btnTransf = h('button', { type: 'button', class: 'seg', onclick: () => setTipo('transferencia') }, 'Transferência');
  const segmento = h('div', { class: 'segmentado' }, btnDesp, btnRec, opts.capturaId ? null : btnTransf);
  const ver = (el, sim) => { el.style.display = sim ? '' : 'none'; };
  const contasTransf = estado.contas.filter(c => !c.inativa && c.papel !== 'leitor');
  const opcoesConta = () => contasTransf.map(c => h('option', { value: c.id }, c.nome + (c.dono_id !== estado.eu.id ? ` (de ${c.dono_nome})` : '')));
  const origem = h('select', null, opcoesConta());
  const destinoT = h('select', null, opcoesConta());
  if (contasTransf.length > 1) destinoT.value = contasTransf[1].id;
  const cOrigem = campo('De (conta de origem)', origem), cDestinoT = campo('Para (conta de destino)', destinoT);

  const valor = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0,00', class: 'valor-grande', autocomplete: 'off',
    value: ini.valor_centavos ? centavosParaCampo(ini.valor_centavos) : '' });
  const data = h('input', { type: 'date', value: ini.data_competencia || hojeISO(), required: true });
  const dataCaixa = h('input', { type: 'date', value: ed ? ed.data_caixa : '' });
  const descricao = h('input', { type: 'text', maxlength: 200, placeholder: 'Ex.: compras da semana', value: ini.descricao || '' });
  // sugestões dos favoritos já cadastrados do dono da conta/cartão escolhido; ao igualar um nome, sugere a categoria padrão dele
  const campoFav = campoFavorecido({ valor: ini.favorecido_nome || '', dono: () => { const d = ed ? null : dest(); return d ? d.dono : null; },
    aoEscolher: (r) => { if (r.categoria_padrao_id && !categoria.value && [...categoria.options].some(o => o.value === r.categoria_padrao_id)) { categoria.value = r.categoria_padrao_id; catEscolhida = categoria.value; } } });
  const favorecido = campoFav.input;
  const destino = h('select', { value: inicialDest }, dests.map(d => h('option', { value: d.valor }, d.rotulo)));
  const categoria = h('select', null);
  const forma = h('select', { value: ini.forma_pagamento || '' }, h('option', { value: '' }, '—'),
    Object.entries(FORMAS).map(([k, v]) => h('option', { value: k }, v)));
  const parcelas = h('input', { type: 'number', min: 1, max: 60, value: ini.parcelas || 1, inputmode: 'numeric' });
  const modoComp = h('select', { value: 'parcela' },
    h('option', { value: 'parcela' }, 'Cada parcela no seu mês'), h('option', { value: 'compra' }, 'Compra inteira no mês da compra'));
  const previsto = h('input', { type: 'checkbox' });
  previsto.checked = (ini.estado || (ed && ed.estado)) === 'previsto';
  const msg = h('p', { class: 'erro-form', hidden: true });

  const blocoModo = campo('Como contar nos relatórios e no orçamento (competência)', modoComp, 'A fatura e o caixa seguem sempre as parcelas; isto só define em que mês o gasto aparece.');
  const blocoParcelas = h('div', { class: 'campo-grupo' }, campo('Parcelas', parcelas, 'Compra parcelada no cartão: cada parcela cai na fatura do mês certo.'), blocoModo);
  const atualizarModo = () => { blocoModo.hidden = !(parseInt(parcelas.value, 10) > 1); };
  parcelas.addEventListener('input', atualizarModo);
  const cData = campo('Data da compra / competência', data);
  const cFav = campo('Favorecido', campoFav.el);
  const cDest = campo('Conta ou cartão', destino);
  const cCat = campo('Categoria', categoria);
  const blocoCaixa = campo('Data de caixa', dataCaixa, 'Quando o dinheiro sai da conta. Deixe em branco para usar a mesma data.');
  const blocoForma = campo('Forma de pagamento', forma);

  const dest = () => dests.find(d => d.valor === destino.value);
  let catEscolhida = ini.categoria_id || (ed && ed.categoria_id) || '';

  function montarCategorias() {
    const d = ed ? dests.find(x => (ed.conta_id && x.valor === `conta:${ed.conta_id}`) || (ed.plastico_id && x.valor === `plastico:${ed.plastico_id}`)) : dest();
    const dono = d ? d.dono : null;
    while (categoria.firstChild) categoria.removeChild(categoria.firstChild);
    categoria.append(h('option', { value: '' }, 'Sem categoria'), ...opcoesCategoria(dono, tipo));
    categoria.value = [...categoria.options].some(o => o.value === catEscolhida) ? catEscolhida : '';
  }
  function atualizarVisibilidade() {
    const d = dest();
    const transf = tipo === 'transferencia';
    const cartao = !transf && (ed ? !!ed.plastico_id : d && d.tipo === 'plastico');
    blocoParcelas.hidden = !!ed || !cartao;
    atualizarModo();
    ver(blocoCaixa, !transf && !cartao);
    ver(blocoForma, !transf && !cartao);
    ver(cFav, !transf); ver(cCat, !transf); ver(cDest, !transf);
    ver(cOrigem, transf); ver(cDestinoT, transf);
    cData.firstChild.textContent = transf ? 'Data da transferência' : 'Data da compra / competência';
  }
  function setTipo(t) {
    tipo = t;
    btnDesp.classList.toggle('ativo', t === 'despesa');
    btnRec.classList.toggle('ativo', t === 'receita');
    btnTransf.classList.toggle('ativo', t === 'transferencia');
    if (t !== 'transferencia') montarCategorias();
    atualizarVisibilidade();
  }
  categoria.addEventListener('change', () => { catEscolhida = categoria.value; });
  destino.addEventListener('change', () => { montarCategorias(); atualizarVisibilidade(); });
  const enviar = h('button', { class: 'btn', type: 'submit' }, ed ? 'Salvar' : opts.capturaId ? 'Confirmar lançamento' : 'Lançar');
  const form = h('form', { class: 'form', novalidate: true },
    ed ? null : segmento,
    campo('Valor (R$)', valor),
    cData,
    cFav,
    campo('Descrição', descricao),
    ed ? h('p', { class: 'dica' }, `Lançado em: ${ed.plastico_id ? `${ed.cartao_nome} ·· ${ed.plastico_final}` : ed.conta_nome}`)
       : cDest,
    cOrigem, cDestinoT,
    cCat,
    blocoForma, blocoCaixa, blocoParcelas,
    h('label', { class: 'check' }, previsto, h('span', null, 'Ainda não aconteceu (previsto)')),
    msg,
    h('div', { class: 'linha-botoes' },
      opts.aoCancelar ? h('button', { type: 'button', class: 'btn sec', onclick: opts.aoCancelar }, 'Cancelar') : null, enviar));

  form.addEventListener('submit', acao_(async () => {
    msg.hidden = true;
    const cent = parseValor(valor.value);
    if (!(cent > 0)) throw new Error('Informe um valor maior que zero.');
    if (!data.value) throw new Error('Informe a data.');
    const nomeFav = favorecido.value.trim();
    if (!ed && tipo === 'transferencia') {
      if (contasTransf.length < 2) throw new Error('Você precisa de pelo menos duas contas para transferir.');
      if (origem.value === destinoT.value) throw new Error('Escolha contas diferentes na origem e no destino.');
      await POST('/api/transferencias', { conta_origem_id: origem.value, conta_destino_id: destinoT.value, valor_centavos: cent,
        data: data.value, descricao: descricao.value.trim() || null, estado: previsto.checked ? 'previsto' : 'confirmado' });
      aviso('Transferência registrada');
      if (opts.aoSalvar) await opts.aoSalvar();
      return;
    }
    if (ed) {
      const corpo = { valor_centavos: cent, descricao: descricao.value, estado: previsto.checked ? 'previsto' : 'confirmado',
        forma_pagamento: forma.value || undefined, categoria_id: categoria.value || undefined, favorecido_nome: nomeFav || undefined };
      if (data.value !== ed.data_competencia) corpo.data_competencia = data.value;
      if (!ed.plastico_id && dataCaixa.value && dataCaixa.value !== ed.data_caixa) corpo.data_caixa = dataCaixa.value;
      await PATCH(`/api/transacoes/${ed.id}`, corpo);
    } else {
      const d = dest();
      if (!d) throw new Error('Cadastre uma conta ou cartão antes de lançar.');
      const corpo = { tipo, valor_centavos: cent, data_competencia: data.value, descricao: descricao.value || null,
        categoria_id: categoria.value || null, favorecido_nome: nomeFav || null, estado: previsto.checked ? 'previsto' : 'confirmado' };
      if (d.tipo === 'plastico') {
        corpo.plastico_id = d.id; corpo.forma_pagamento = 'cartao';
        corpo.parcelas = Math.max(1, Math.min(60, parseInt(parcelas.value, 10) || 1));
        corpo.competencia_parcelas = corpo.parcelas > 1 ? modoComp.value : 'parcela';
      } else {
        corpo.conta_id = d.id; corpo.forma_pagamento = forma.value || null;
        if (dataCaixa.value) corpo.data_caixa = dataCaixa.value;
      }
      if (opts.capturaId) await POST(`/api/capturas/${opts.capturaId}/confirmar`, corpo);
      else await POST('/api/transacoes', { ...corpo, anexo_id: opts.anexoId || null });
    }
    aviso(ed ? 'Lançamento atualizado' : 'Lançamento salvo');
    if (opts.aoSalvar) await opts.aoSalvar();
  }, enviar, msg));

  setTipo(tipo);
  return form;
}

// envolve o handler de submit: bloqueia o botão e mostra erros no próprio formulário
function acao_(fn, botao, msg) {
  return async (e) => {
    e.preventDefault();
    if (botao.disabled) return;
    botao.disabled = true;
    try { await fn(); } catch (err) { msg.textContent = err.message || 'Erro'; msg.hidden = false; msg.scrollIntoView({ block: 'nearest' }); } finally { botao.disabled = false; }
  };
}

export async function excluirTransacao(t) {
  let todo = false;
  if (t.parcelamento_id && t.total_parcelas > 1) {
    const r = await new Promise((res) => folha('Excluir parcela', (corpo, fechar) => {
      corpo.append(h('p', null, `Esta é a parcela ${t.numero_parcela}/${t.total_parcelas} de uma compra parcelada.`),
        h('div', { class: 'coluna-botoes' },
          h('button', { class: 'btn perigo', onclick: () => { fechar(); res('uma'); } }, 'Excluir só esta parcela'),
          h('button', { class: 'btn perigo', onclick: () => { fechar(); res('todas'); } }, 'Excluir todas as parcelas'),
          h('button', { class: 'btn sec', onclick: () => { fechar(); res(null); } }, 'Cancelar')));
    }));
    if (!r) return false;
    todo = r === 'todas';
  } else if (!(await confirmar(t.transferencia_id ? 'Excluir esta transferência? As duas pontas (origem e destino) serão apagadas.'
      : t.recorrencia_id ? 'Este lançamento vem de uma recorrência. Excluir só este mês? A recorrência continua valendo nos próximos meses (você pode desfazer em Mais → Lançamentos recorrentes).'
      : 'Excluir este lançamento?', t.recorrencia_id ? 'Excluir só este mês' : 'Excluir', true))) return false;
  await DEL(`/api/transacoes/${t.id}${todo ? '?todo_parcelamento=true' : ''}`);
  aviso(t.recorrencia_id ? 'Mês pulado na recorrência' : 'Lançamento excluído');
  return true;
}
