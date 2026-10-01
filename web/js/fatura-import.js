// Importar fatura de cartão (PDF): lê com IA, compara com o que já foi lançado e deixa conferir antes de gravar.
import { h, api, POST, brl, folha, aviso, acao, campo, limpar, dataCurta, dataLonga } from './util.js';
import { estado, opcoesCategoria } from './form.js';

export function importarFatura(k, aoTerminar) {
  folha('Importar fatura (PDF)', (corpo, fechar) => {
    const arquivo = h('input', { type: 'file', accept: 'application/pdf,.pdf' });
    const senha = h('input', { type: 'password', autocomplete: 'off', placeholder: 'Senha do PDF, se tiver' });
    const botao = h('button', { class: 'btn', onclick: acao(async (e) => {
      if (!arquivo.files[0]) return aviso('Escolha o PDF da fatura', true);
      const fd = new FormData();
      fd.append('arquivo', arquivo.files[0]);
      fd.append('cartao_id', k.id);
      fd.append('senha', senha.value);
      limpar(corpo).append(h('div', { class: 'cartao carregando' }, h('div', { class: 'spinner' }), h('p', null, 'Lendo a fatura… pode levar até um minuto.')));
      try {
        const previa = await api('POST', '/api/faturas/importar/ler', fd);
        conferir(corpo, fechar, k, previa, aoTerminar);
      } catch (err) { limpar(corpo); formulario(); aviso(err.message, true); }
    }) }, 'Ler fatura');
    function formulario() {
      limpar(corpo).append(
        h('p', { class: 'dica' }, `Escolha a fatura em PDF de ${k.nome}. Se o arquivo tiver senha, informe-a: ela é usada só para abrir o arquivo agora e não fica guardada. Nada é gravado antes de você conferir.`),
        campo('Arquivo da fatura', arquivo), campo('Senha do PDF (opcional)', senha), botao);
    }
    formulario();
  });
}

function conferir(corpo, fechar, k, p, aoTerminar) {
  const ehCartaoDono = k.dono_id;
  const linhas = p.linhas.map(l => ({
    ...l, acao: l.acao_sugerida, incluir: l.acao_sugerida === 'criar', futuras: true,
    usarFatura: l.acao_sugerida === 'atualizar',
  }));
  const contador = h('b');
  const aplicar = h('button', { class: 'btn', onclick: acao(async () => {
    const envio = [];
    for (const l of linhas) {
      let a = 'ignorar';
      if (l.casamento) a = l.usarFatura ? 'atualizar' : 'conferir';
      else if (l.incluir) a = 'criar';
      if (a === 'ignorar') continue;
      envio.push({ acao: a, transacao_id: l.casamento ? l.casamento.transacao_id : null, data: l.data, descricao: l.descricao,
        favorecido_id: l.favorecido_id, favorecido_nome: l.favorecido_nome, categoria_id: l.categoria_id || null, plastico_id: l.plastico_id,
        valor_centavos: l.valor_centavos, eh_credito: l.eh_credito, parcela_atual: l.parcela_atual, parcelas_total: l.parcelas_total,
        criar_futuras: !l.casamento && l.futuras && l.parcelas_total > l.parcela_atual && !l.eh_credito });
    }
    const r = await POST('/api/faturas/importar/aplicar', { cartao_id: k.id, vencimento: p.fatura.vencimento, linhas: envio });
    aviso(`${r.criadas} lançamento(s) criado(s), ${r.atualizadas} atualizado(s)` + (r.futuras ? `, ${r.futuras} parcela(s) futura(s) prevista(s)` : ''));
    fechar(); aoTerminar();
  }) }, 'Aplicar');
  const recontar = () => {
    const novas = linhas.filter(l => !l.casamento && l.incluir).length;
    const atual = linhas.filter(l => l.casamento && l.usarFatura).length;
    const fut = linhas.reduce((n, l) => n + (!l.casamento && l.incluir && l.futuras && !l.eh_credito && l.parcelas_total > l.parcela_atual ? l.parcelas_total - l.parcela_atual : 0), 0);
    contador.textContent = `${novas} nova(s), ${atual} atualizada(s)` + (fut ? `, +${fut} parcela(s) futura(s)` : '');
  };

  const f = p.fatura;
  const dif = f.diferenca_centavos;
  const cab = h('section', { class: 'cartao' },
    h('b', null, `${f.emissor || 'Fatura'} · vence ${dataLonga(f.vencimento)}`),
    h('small', { class: 'dica' }, `Fecha ${dataCurta(f.fechamento)} · ${k.nome}`),
    h('div', { class: 'tres' },
      h('div', null, h('small', null, 'Total da fatura'), h('b', null, brl(f.total_centavos))),
      h('div', null, h('small', null, 'Compras lidas'), h('b', null, brl(f.soma_compras_centavos))),
      h('div', null, h('small', null, 'Diferença'), h('b', { class: dif ? 'neg' : 'pos' }, brl(Math.abs(dif))))),
    h('small', { class: 'dica' }, 'Os valores aparecem como na fatura: compras positivas; créditos e estornos aparecem como crédito, e reduzem a fatura. Ao gravar, cada compra entra como despesa do cartão.'),
    dif ? h('small', { class: 'dica' }, 'A diferença pode ser encargos, anuidade, saldo anterior ou uma linha que a leitura não pegou. Confira as linhas abaixo com a fatura.') : null,
    p.alertas.map(a => h('p', { class: 'alertas' }, a)));

  const dono = k.dono_id;
  function seletorCategoria(l) {
    const tipo = l.eh_credito ? 'receita' : 'despesa';
    const sel = h('select', { onchange: () => {
      l.categoria_id = sel.value || null; l.manual = true;
      // mesma loja nas outras linhas novas: acompanha a escolha (exceto as que você já ajustou)
      for (const o of linhas) if (o !== l && !o.casamento && !o.manual && (o.favorecido_nome || '').toLowerCase() === (l.favorecido_nome || '').toLowerCase() && o.seletor) { o.categoria_id = l.categoria_id; o.seletor.value = sel.value; }
    } }, h('option', { value: '' }, 'Sem categoria'), opcoesCategoria(dono, tipo));
    l.seletor = sel;
    sel.value = l.categoria_id || '';
    if (sel.value !== (l.categoria_id || '')) sel.value = '';
    return sel;
  }
  const rotuloParcela = (l) => l.parcelas_total > 1 ? ` · ${l.parcela_atual}/${l.parcelas_total}` : '';
  // valores como na fatura do banco: compra positiva; crédito/estorno rotulado (reduz a fatura)
  const valorTxt = (l) => l.eh_credito ? `crédito −${brl(l.valor_centavos)}` : brl(l.valor_centavos);

  function linhaJa(l) {
    const c = l.casamento;
    const dd = c.diferenca_centavos;
    const bloco = h('div', { class: 'imp-linha' },
      h('div', { class: 'imp-topo' }, h('div', { class: 'corpo' }, h('b', null, l.descricao), h('small', null, `${dataCurta(l.data)}${rotuloParcela(l)} · ${l.plastico_rotulo}`)), h('b', null, valorTxt(l))));
    if (!dd && c.data === l.data) { bloco.append(h('small', { class: 'selo' }, '✓ confere')); return bloco; }
    if (dd) {
      bloco.append(h('p', { class: 'imp-dif' }, `No app: ${brl(c.valor_centavos)} · Na fatura: ${brl(l.valor_centavos)} · `, h('b', null, `${brl(Math.abs(dd))} ${dd > 0 ? 'a mais' : 'a menos'} na fatura`)));
    }
    if (c.data !== l.data) bloco.append(h('small', { class: 'dica' }, `Data no app: ${dataCurta(c.data)} · na fatura: ${dataCurta(l.data)}`));
    const sel = h('select', { onchange: () => { l.usarFatura = sel.value === 'fatura'; recontar(); } },
      h('option', { value: 'fatura' }, 'Usar o valor/data da fatura'), h('option', { value: 'app' }, 'Manter o que está no app'));
    sel.value = l.usarFatura ? 'fatura' : 'app';
    bloco.append(sel);
    return bloco;
  }
  function linhaNova(l, padraoMarcado) {
    const marca = h('input', { type: 'checkbox', onchange: () => { l.incluir = marca.checked; recontar(); } });
    marca.checked = l.incluir;
    const nome = h('input', { type: 'text', value: l.favorecido_nome || '', maxlength: 120, 'aria-label': 'Favorecido', onchange: () => { l.favorecido_nome = nome.value.trim(); l.favorecido_id = null; } });
    const resta = l.parcelas_total - l.parcela_atual;
    let futuras = null;
    if (resta > 0 && !l.eh_credito) {
      const ult = new Date(`${p.fatura.vencimento}T12:00:00`);
      ult.setMonth(ult.getMonth() + resta);
      const caixa = h('input', { type: 'checkbox', onchange: () => { l.futuras = caixa.checked; recontar(); } });
      caixa.checked = l.futuras;
      futuras = h('label', { class: 'imp-futuras' }, caixa,
        h('span', null, `Criar também as ${resta} parcela(s) futura(s) como previstas: ${resta} × ${brl(l.valor_centavos)}, até ${String(ult.getMonth() + 1).padStart(2, '0')}/${ult.getFullYear()}`));
    }
    return h('div', { class: 'imp-linha' },
      h('label', { class: 'imp-topo' }, marca, h('div', { class: 'corpo' }, h('b', null, l.descricao), h('small', null, `${dataCurta(l.data)}${rotuloParcela(l)} · ${l.plastico_rotulo}${l.motivo ? ' · ' + l.motivo : ''}`)), h('b', null, valorTxt(l))),
      l.alerta ? h('small', { class: 'dica' }, l.alerta) : null,
      h('div', { class: 'duas' }, nome, seletorCategoria(l)), futuras);
  }

  const ja = linhas.filter(l => l.casamento), novas = linhas.filter(l => !l.casamento && l.acao === 'criar'), fora = linhas.filter(l => !l.casamento && l.acao === 'ignorar');
  limpar(corpo).append(cab,
    ja.length ? h('h3', null, `Já lançadas no app (${ja.length})`) : null, ja.map(linhaJa),
    novas.length ? h('h3', null, `Novas na fatura (${novas.length})`) : null, novas.map(l => linhaNova(l)),
    fora.length ? h('h3', null, `Fora da carga (${fora.length})`) : null,
    fora.length ? h('small', { class: 'dica' }, 'Pagamentos, encargos e itens que não são compras. Marque só o que quiser lançar.') : null, fora.map(l => linhaNova(l)),
    p.no_app_sem_par.length ? h('h3', null, `No app, mas não na fatura (${p.no_app_sem_par.length})`) : null,
    p.no_app_sem_par.length ? h('small', { class: 'dica' }, 'Estão lançadas nesta fatura no app e não apareceram no PDF. Nada é alterado aqui; revise em Lançamentos.') : null,
    p.no_app_sem_par.map(x => h('div', { class: 'imp-linha' }, h('div', { class: 'imp-topo' }, h('div', { class: 'corpo' }, h('b', null, x.descricao || '—'), h('small', null, dataCurta(x.data))), h('b', null, x.eh_credito ? `crédito −${brl(x.valor_centavos)}` : brl(x.valor_centavos))))),
    h('div', { class: 'imp-rodape' }, h('small', null, contador), aplicar));
  recontar();
}
