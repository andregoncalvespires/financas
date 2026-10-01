import { h, GET, POST, PATCH, DEL, brl, folha, aviso, acao, campo, limpar, vazio, dataCurta, dataLonga, parseValor, centavosParaCampo, hojeISO, confirmar } from './util.js';
import { estado, carregarCadastros } from './form.js';
import { detalhe } from './lanc.js';

const TIPO = { plastico: 'Plástico', virtual: 'Virtual' };
const rotuloCartao = (p) => `·· ${p.final} ${TIPO[p.tipo] || ''}`.trim();

export async function cartoes(raiz, ctx) {
  await carregarCadastros();
  const meus = estado.cartoes.filter(k => k.sou_dono);
  const portador = estado.cartoes.some(k => !k.sou_dono);
  const recarregar = () => cartoes(raiz, ctx);
  limpar(raiz).append(h('h1', null, 'Contas de cartão'),
    h('p', { class: 'dica' }, 'Cada conta de cartão tem uma fatura. Dentro dela ficam os cartões: o principal (Plástico) e os adicionais (Plástico ou Virtual).'),
    meus.length ? meus.map(k => cartaoDono(k, recarregar)) : vazio('Você ainda não cadastrou contas de cartão.'),
    h('button', { class: 'btn sec', onclick: () => novoCartao(recarregar) }, '+ Nova conta de cartão'),
    portador ? h('div', { id: 'meus-gastos' }) : null);
  if (portador) await meusGastos(raiz.querySelector('#meus-gastos'));
}

function cartaoDono(k, recarregar) {
  const corpo = h('div', { class: 'faturas' });
  const ativos = k.plasticos.filter(p => p.ativo).length;
  const det = h('details', { class: 'cartao' },
    h('summary', null, h('div', null, h('b', null, k.nome), k.inativo ? h('small', { class: 'selo aviso' }, 'inativa') : null,
        h('small', { class: 'selo' }, `fecha dia ${k.dia_fechamento} · vence dia ${k.dia_vencimento}`)),
      h('small', null, `${ativos} cartão(ões)`)),
    !k.conta_pagamento_id ? h('p', { class: 'alertas' }, 'Sem conta de pagamento definida: as faturas desta conta de cartão não entram no "disponível de verdade". Toque em Editar.') : null,
    h('div', { class: 'linha-botoes' }, h('button', { class: 'btn sec', onclick: () => editarCartao(k, recarregar) }, 'Editar conta de cartão')),
    h('h3', null, 'Cartões'),
    k.plasticos.map(p => linhaPlastico(k, p, recarregar)),
    h('button', { class: 'btn link', onclick: () => novoPlastico(k, recarregar) }, '+ Adicionar cartão (adicional)'),
    h('h3', null, 'Faturas'), corpo);
  let carregado = false;
  det.addEventListener('toggle', async () => {
    if (!det.open || carregado) return;
    carregado = true;
    await listarFaturas(k, corpo, recarregar);
  });
  return det;
}

function linhaPlastico(k, p, recarregar) {
  return h('button', { class: 'linha item', onclick: () => editarPlastico(k, p, recarregar) },
    h('div', { class: 'corpo' }, h('b', null, `·· ${p.final} `, h('small', { class: 'selo' }, p.principal ? 'Plástico · principal' : TIPO[p.tipo]),
        !p.ativo ? h('small', { class: 'selo aviso' }, 'inativo') : null),
      h('small', null, p.rotulo + (p.portador_nome ? ` · portador: ${p.portador_nome}` : ' · sem portador vinculado'))),
    h('span', null, '›'));
}

// ---------- faturas e itens ----------
async function listarFaturas(k, corpo, recarregar) {
  const fats = await GET(`/api/cartoes/${k.id}/faturas`);
  limpar(corpo);
  if (!fats.length) return corpo.append(vazio('Nenhuma fatura ainda: elas aparecem quando há compras.'));
  for (const f of fats) {
    const itens = h('div', { class: 'itens-fatura' });
    const det = h('details', { class: 'cartao interno' },
      h('summary', null, h('div', { class: 'corpo' }, h('b', null, `Vence ${dataLonga(f.data_vencimento)}`),
          h('small', null, `fecha ${dataCurta(f.data_fechamento)} · ${f.itens} compra(s)`)),
        h('div', { class: 'direita' }, h('b', null, brl(-f.total)), h('small', { class: 'selo ' + (f.status === 'paga' ? '' : 'aviso') }, f.status === 'paga' ? 'paga' : 'aberta'))),
      f.por_plastico.length > 1 ? h('ul', { class: 'quebra' }, f.por_plastico.map(q => h('li', null, `·· ${q.final} ${q.portador_nome ? '(' + q.portador_nome + ')' : q.rotulo}: `, h('b', null, brl(-q.total))))) : null,
      itens,
      f.status === 'paga'
        ? h('button', { class: 'btn link', disabled: !f.pagamento_transacao_id, onclick: acao(async () => {
            if (!(await confirmar('Desfazer o pagamento? O lançamento de pagamento será excluído e a fatura volta a ficar aberta.', 'Desfazer', true))) return;
            await DEL(`/api/transacoes/${f.pagamento_transacao_id}`);
            aviso('Pagamento desfeito'); recarregar();
          }) }, 'Desfazer pagamento')
        : h('button', { class: 'btn', onclick: () => pagarFatura(k, f, recarregar) }, 'Marcar como paga'));
    let feito = false;
    det.addEventListener('toggle', async () => {
      if (!det.open || feito) return;
      feito = true;
      const url = `/api/transacoes?fatura_id=${f.id}&limite=1000`;
      const de_novo = () => carregarItens(itens, url, true, de_novo);
      await de_novo();
    });
    corpo.append(det);
  }
}

async function carregarItens(alvo, url, mostrarCartao, aoMudar) {
  limpar(alvo).append(h('div', { class: 'spinner' }));
  try {
    const ts = (await GET(url)).sort((a, b) => String(a.data_compra || a.data_competencia).localeCompare(String(b.data_compra || b.data_competencia)));
    limpar(alvo);
    if (!ts.length) return alvo.append(vazio('Sem compras.'));
    for (const t of ts) {
      const sub = [t.categoria_nome, mostrarCartao ? `·· ${t.plastico_final}` : null, t.total_parcelas ? `parcela ${t.numero_parcela}/${t.total_parcelas}` : null,
        mostrarCartao && t.criado_por_nome ? `por ${t.criado_por_nome}` : null].filter(Boolean).join(' · ');
      alvo.append(h('button', { class: 'linha item', onclick: () => detalhe(t, aoMudar || (() => {})) },
        h('div', { class: 'corpo' }, h('b', null, `${dataCurta(t.data_compra || t.data_competencia)} · ${t.favorecido_nome || t.descricao || 'Sem descrição'}`), h('small', null, sub)),
        h('b', { class: t.valor_centavos < 0 ? 'neg' : 'pos' }, brl(-t.valor_centavos))));
    }
  } catch (e) { limpar(alvo).append(h('p', { class: 'erro-form' }, e.message)); }
}

export function pagarFatura(k, f, recarregar) {
  folha('Pagar fatura', (corpo, fechar) => {
    const contas = estado.contas.filter(c => !c.inativa && c.papel !== 'leitor');
    const conta = h('select', { value: k.conta_pagamento_id || (contas[0] && contas[0].id) }, contas.map(c => h('option', { value: c.id }, c.nome)));
    const data = h('input', { type: 'date', value: hojeISO() });
    const total = f.total !== undefined ? f.total : f.valor_centavos;
    const valor = h('input', { type: 'text', inputmode: 'decimal', value: centavosParaCampo(total) });
    corpo.append(h('p', null, `${k.nome} · vence ${dataLonga(f.data_vencimento || f.data)}`),
      campo('Paga com a conta', conta), campo('Data do pagamento', data), campo('Valor pago (R$)', valor),
      h('button', { class: 'btn', onclick: acao(async () => {
        const v = parseValor(valor.value);
        if (!(v > 0)) throw new Error('Valor inválido');
        await POST(`/api/faturas/${f.id}/pagar`, { conta_id: conta.value, data: data.value, valor_centavos: v });
        fechar(); aviso('Fatura marcada como paga'); if (recarregar) recarregar();
      }) }, 'Confirmar pagamento'));
  });
}

// ---------- conta de cartão: criar / editar / excluir ----------
function camposCartao(k, contas) {
  const nome = h('input', { type: 'text', placeholder: 'Ex.: Visa Itaú', value: k ? k.nome : '' });
  const bandeira = h('input', { type: 'text', placeholder: 'Visa, Master…', value: k && k.bandeira || '' });
  const fech = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', value: k ? k.dia_fechamento : '' });
  const venc = h('input', { type: 'number', min: 1, max: 31, inputmode: 'numeric', value: k ? k.dia_vencimento : '' });
  const limite = h('input', { type: 'text', inputmode: 'decimal', placeholder: 'opcional', value: k && k.limite_centavos ? centavosParaCampo(k.limite_centavos) : '' });
  const conta = h('select', { value: k ? (k.conta_pagamento_id || '') : (contas[0] ? contas[0].id : '') }, h('option', { value: '' }, 'Escolher depois'), contas.map(c => h('option', { value: c.id }, c.nome)));
  const valores = () => {
    if (!nome.value.trim() || !fech.value || !venc.value) throw new Error('Preencha nome, fechamento e vencimento.');
    const lim = limite.value.trim() ? parseValor(limite.value) : null;
    if (Number.isNaN(lim)) throw new Error('Limite inválido.');
    return { nome: nome.value.trim(), bandeira: bandeira.value.trim() || null, dia_fechamento: +fech.value, dia_vencimento: +venc.value, conta_pagamento_id: conta.value || null, limite_centavos: lim };
  };
  const nodes = [campo('Nome', nome), campo('Bandeira', bandeira), campo('Dia de fechamento', fech, 'Compras até este dia (inclusive) entram na fatura do mês.'),
    campo('Dia de vencimento', venc), campo('Conta que paga a fatura', conta), campo('Limite (R$)', limite)];
  return { nodes, valores };
}

function novoCartao(recarregar) {
  folha('Nova conta de cartão', (corpo, fechar) => {
    const contas = estado.contas.filter(c => !c.inativa && c.papel !== 'leitor');
    const { nodes, valores } = camposCartao(null, contas);
    const final = h('input', { type: 'text', maxlength: 4, inputmode: 'numeric', placeholder: '1234' });
    corpo.append(nodes[0], campo('Final do cartão principal (Plástico)', final), ...nodes.slice(1),
      h('button', { class: 'btn', onclick: acao(async () => {
        const b = valores();
        if (final.value) b.final_principal = final.value;
        await POST('/api/cartoes', b);
        fechar(); aviso('Conta de cartão criada'); recarregar();
      }) }, 'Criar'));
  });
}

function editarCartao(k, recarregar) {
  folha(`Editar ${k.nome}`, (corpo, fechar) => {
    const contas = estado.contas.filter(c => !c.inativa && c.papel !== 'leitor');
    const { nodes, valores } = camposCartao(k, contas);
    corpo.append(...nodes,
      h('p', { class: 'dica' }, 'Mudar fechamento ou vencimento ajusta as faturas abertas que ainda não fecharam. Compras já lançadas continuam na fatura em que estão.'),
      h('button', { class: 'btn', onclick: acao(async () => {
        const r = await PATCH(`/api/cartoes/${k.id}`, valores());
        fechar(); aviso(r.faturas_recalculadas ? `Salvo. ${r.faturas_recalculadas} fatura(s) aberta(s) ajustada(s).` : 'Salvo'); recarregar();
      }) }, 'Salvar'),
      h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/cartoes/${k.id}`, { inativo: !k.inativo }); fechar(); recarregar(); }) }, k.inativo ? 'Reativar' : 'Inativar'),
        h('button', { class: 'btn sec perigo-txt', onclick: acao(async () => { await excluirCartao(k); fechar(); recarregar(); }) }, 'Excluir')));
  });
}

async function excluirCartao(k) {
  if (!(await confirmar(`Excluir a conta de cartão "${k.nome}"?`, 'Excluir', true))) throw new Error('Exclusão cancelada');
  try { await DEL(`/api/cartoes/${k.id}`); aviso('Excluída'); }
  catch (e) {
    if (e.status !== 409) throw e;
    if (!(await confirmar(`${e.message}\n\nExcluir mesmo assim apaga também todas as compras e faturas. Prefere apenas inativar? Cancele e use "Inativar".`, 'Excluir com todas as compras', true))) throw new Error('Exclusão cancelada');
    const r = await DEL(`/api/cartoes/${k.id}?com_historico=true`);
    aviso(`Excluída, com ${r.compras_excluidas} compra(s)`);
  }
}

// ---------- cartões (plástico/virtual) ----------
function novoPlastico(k, recarregar) {
  folha('Novo cartão adicional', (corpo, fechar) => {
    const final = h('input', { type: 'text', maxlength: 4, inputmode: 'numeric', placeholder: '5678' });
    const rotulo = h('input', { type: 'text', placeholder: 'Ex.: Maria, compras online' });
    const tipo = h('select', { value: 'plastico' }, h('option', { value: 'plastico' }, 'Plástico'), h('option', { value: 'virtual' }, 'Virtual'));
    corpo.append(h('p', { class: 'dica' }, 'As compras deste cartão entram na fatura desta conta de cartão. Depois você pode convidar quem o usa.'),
      campo('Final (4 dígitos)', final), campo('Identificação', rotulo), campo('Tipo', tipo),
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!/^\d{4}$/.test(final.value) || !rotulo.value.trim()) throw new Error('Informe os 4 dígitos e uma identificação.');
        await POST(`/api/cartoes/${k.id}/plasticos`, { final: final.value, rotulo: rotulo.value.trim(), tipo: tipo.value });
        fechar(); aviso('Cartão adicionado'); recarregar();
      }) }, 'Adicionar'));
  });
}

function editarPlastico(k, p, recarregar) {
  folha(`Cartão ·· ${p.final}`, (corpo, fechar) => {
    const final = h('input', { type: 'text', maxlength: 4, inputmode: 'numeric', value: p.final });
    const rotulo = h('input', { type: 'text', value: p.rotulo });
    const tipo = h('select', { value: p.tipo, disabled: p.principal }, h('option', { value: 'plastico' }, 'Plástico'), h('option', { value: 'virtual' }, 'Virtual'));
    corpo.append(campo('Final (4 dígitos)', final), campo('Identificação', rotulo),
      campo('Tipo', tipo, p.principal ? 'O cartão principal é sempre Plástico.' : null),
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!/^\d{4}$/.test(final.value) || !rotulo.value.trim()) throw new Error('Informe os 4 dígitos e uma identificação.');
        await PATCH(`/api/plasticos/${p.id}`, { final: final.value, rotulo: rotulo.value.trim(), tipo: tipo.value });
        fechar(); aviso('Salvo'); recarregar();
      }) }, 'Salvar'));
    if (!p.principal) {
      corpo.append(h('div', { class: 'linha-botoes' },
        p.tipo === 'plastico' && p.ativo ? h('button', { class: 'btn sec', onclick: acao(async () => {
          if (!(await confirmar(`Tornar ·· ${p.final} o cartão principal desta conta de cartão?`, 'Tornar principal'))) return;
          await PATCH(`/api/plasticos/${p.id}`, { principal: true }); fechar(); recarregar();
        }) }, 'Tornar principal') : null,
        h('button', { class: 'btn sec', onclick: acao(async () => { await PATCH(`/api/plasticos/${p.id}`, { ativo: !p.ativo }); fechar(); recarregar(); }) }, p.ativo ? 'Inativar' : 'Reativar')));
    }
    corpo.append(h('h3', null, 'Portador'));
    corpo.append(p.portador_id
      ? h('div', null, h('p', { class: 'dica' }, `Vinculado a ${p.portador_nome}. Ele vê só o que gastou neste cartão.`),
          h('button', { class: 'btn sec', onclick: acao(async () => { if (await confirmar(`Desvincular ${p.portador_nome} deste cartão?`, 'Desvincular')) { await DEL(`/api/plasticos/${p.id}/portador`); fechar(); recarregar(); } }) }, 'Desvincular portador'))
      : h('button', { class: 'btn sec', onclick: () => { fechar(); convidarPortador(p, recarregar); } }, 'Convidar portador'));
    if (!p.principal) {
      corpo.append(h('button', { class: 'btn link perigo', onclick: acao(async () => {
        if (!(await confirmar(`Excluir o cartão ·· ${p.final}?`, 'Excluir', true))) return;
        try { await DEL(`/api/plasticos/${p.id}`); fechar(); aviso('Cartão excluído'); recarregar(); }
        catch (e) { if (e.status === 409) aviso(`${e.message}`, true); else throw e; }
      }) }, 'Excluir cartão'));
    }
  });
}

function convidarPortador(p, recarregar) {
  folha(`Portador do cartão ·· ${p.final}`, (corpo, fechar) => {
    const email = h('input', { type: 'email', placeholder: 'email@exemplo.com', autocomplete: 'off' });
    corpo.append(h('p', { class: 'dica' }, 'A pessoa recebe um convite por e-mail. Ao aceitar, ela lança as compras deste cartão e vê apenas o que ela mesma gastou; o gasto entra na sua fatura.'),
      campo('E-mail da pessoa', email),
      h('button', { class: 'btn', onclick: acao(async () => {
        if (!email.value.includes('@')) throw new Error('E-mail inválido.');
        await POST(`/api/plasticos/${p.id}/convites`, { email: email.value.trim() });
        fechar(); aviso('Convite enviado'); recarregar();
      }) }, 'Enviar convite'));
  });
}

// ---------- visão do portador ----------
async function meusGastos(alvo) {
  const lista = await GET('/api/portador/meus-gastos');
  if (!lista.length) return;
  alvo.append(h('h2', null, 'Meus gastos em cartões de outras pessoas'),
    h('p', { class: 'dica' }, 'Você vê só o que gastou nestes cartões; o total da fatura é do dono.'));
  for (const p of lista) {
    alvo.append(h('section', { class: 'cartao' },
      h('b', null, `${p.cartao_nome} ${rotuloCartao(p)}`), h('small', null, ` de ${p.dono_nome} · próxima fatura vence ${dataLonga(p.vencimento_atual)}`),
      p.faturas.length ? p.faturas.map(f => {
        const itens = h('div', { class: 'itens-fatura' });
        let feito = false;
        const det = h('details', { class: 'cartao interno' },
          h('summary', null, h('div', { class: 'corpo' }, h('b', null, `Vencimento ${dataCurta(f.vencimento)}`), h('small', null, `${f.itens} compra(s)`)), h('b', null, brl(-f.total))), itens);
        det.addEventListener('toggle', async () => {
          if (!det.open || feito) return;
          feito = true;
          await carregarItens(itens, `/api/transacoes?plastico_id=${p.plastico_id}&base=caixa&de=${String(f.vencimento).slice(0, 10)}&ate=${String(f.vencimento).slice(0, 10)}&limite=500`, false);
        });
        return det;
      }) : vazio('Sem compras ainda.')));
  }
}
