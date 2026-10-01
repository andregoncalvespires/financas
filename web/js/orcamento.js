import { h, GET, PUT_, DEL, brl, folha, aviso, acao, campo, limpar, vazio, mesISO, somarMes, nomeMes, parseValor, centavosParaCampo, confirmar } from './util.js';
import { estado } from './form.js';

const filtro = { mes: mesISO(), dono: null };

export async function orcamento(raiz, ctx) {
  const donos = await GET('/api/orcamento/donos');
  if (!filtro.dono || !donos.some(d => d.id === filtro.dono)) filtro.dono = estado.eu.id;
  const o = await GET(`/api/orcamento?mes=${filtro.mes}&dono_id=${filtro.dono}`);
  const recarregar = () => orcamento(raiz, ctx);
  const ir = (n) => { filtro.mes = somarMes(filtro.mes, n); recarregar(); };

  limpar(raiz).append(
    h('h1', null, 'Orçamento'),
    h('div', { class: 'navmes' }, h('button', { class: 'icone', 'aria-label': 'Mês anterior', onclick: () => ir(-1) }, '‹'),
      h('b', null, nomeMes(filtro.mes)), h('button', { class: 'icone', 'aria-label': 'Próximo mês', onclick: () => ir(1) }, '›')),
    donos.length > 1 ? campo('Orçamento de', h('select', { value: filtro.dono, onchange: (e) => { filtro.dono = e.target.value; recarregar(); } },
      donos.map(d => h('option', { value: d.id }, d.id === estado.eu.id ? 'Meu orçamento' : d.nome)))) : null,
    !o.pode_editar ? h('p', { class: 'alertas' }, `Somente consulta. O realizado mostra apenas os lançamentos que você tem permissão de ver.`) : null,
    resumo(o),
    secao('Despesas', o.despesas, 'despesa', o, recarregar),
    secao('Receitas', o.receitas, 'receita', o, recarregar),
    o.pode_editar ? h('button', { class: 'btn sec', onclick: () => preencherMedia(recarregar) }, 'Preencher com a média dos últimos 3 meses') : null,
    o.pode_editar ? h('p', { class: 'dica' }, 'Toque numa categoria para definir o valor. "Realizado" são lançamentos confirmados da competência do mês; "previsto" ainda vai acontecer.') : null);
}

function resumo(o) {
  const d = o.despesas, r = o.receitas;
  const col = (rot, v) => h('div', null, h('small', null, rot), h('b', null, brl(v)));
  return h('section', { class: 'cartao' },
    h('div', { class: 'cab-orc' }, col('Receitas orçadas', r.orcado), col('Despesas orçadas', d.orcado), col('Sobra orçada', r.orcado - d.orcado)),
    h('div', { class: 'cab-orc', style: 'margin-top:8px' }, col('Receitas reais', r.realizado), col('Despesas reais', d.realizado), col('Resultado real', r.realizado - d.realizado)));
}

function barra(orc, real, prev, despesa) {
  const escala = Math.max(orc, real + prev, 1);
  return h('div', { class: 'progresso ' + (despesa && real + prev > orc && orc > 0 ? 'estourou' : '') },
    h('div', { class: 'real', style: `width:${real / escala * 100}%` }), h('div', { class: 'prev', style: `width:${prev / escala * 100}%` }));
}

function secao(titulo, bloco, tipo, o, recarregar) {
  const despesa = tipo === 'despesa';
  return h('section', null, h('h2', null, `${titulo} · ${brl(bloco.realizado)} de ${brl(bloco.orcado)}`),
    bloco.grupos.length ? bloco.grupos.map(g => h('details', { class: 'cartao orc-grupo' },
      h('summary', null, h('div', { class: 'corpo', style: 'flex:1' }, h('b', null, g.nome), h('small', null, `${brl(g.realizado)} de ${brl(g.orcado)}${g.previsto ? ` · previsto ${brl(g.previsto)}` : ''}`)),
        h('span', { class: 'pilula' }, g.orcado ? `${Math.round(g.realizado / g.orcado * 100)}%` : '—')),
      barra(g.orcado, g.realizado, g.previsto, despesa),
      g.categorias.map(c => linha(c, despesa, o, recarregar)))) : vazio(`Sem ${titulo.toLowerCase()} neste mês.`));
}

function linha(c, despesa, o, recarregar) {
  const resta = c.orcado - c.realizado - c.previsto;
  const txt = !c.orcado ? 'sem meta' : resta >= 0 ? `${despesa ? 'resta' : 'falta'} ${brl(resta)}` : `${despesa ? 'estourou' : 'acima'} ${brl(-resta)}`;
  return h('div', { class: 'orc-linha', role: o.pode_editar ? 'button' : null, tabindex: o.pode_editar ? 0 : null,
    onclick: o.pode_editar ? () => editar(c, o, recarregar) : null },
    h('div', { class: 'topo' }, h('span', { class: c.ativa ? '' : 'riscado' }, c.nome, c.especifico ? h('small', { class: 'selo' }, 'ajuste do mês') : (c.regra && c.regra.modo !== 'continuo' ? h('small', { class: 'selo' }, c.regra.modo === 'meses' ? 'meses do ano' : 'prazo definido') : null)), h('b', null, `${brl(c.realizado)} / ${brl(c.orcado)}`)),
    barra(c.orcado, c.realizado, c.previsto, despesa),
    h('small', null, h('span', null, c.previsto ? `previsto ${brl(c.previsto)}` : ''), h('span', { class: !c.orcado ? '' : resta < 0 && despesa ? 'neg' : '' }, txt)));
}

const MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
const rotuloMes = (ym) => { const [a, m] = ym.split('-'); return `${MESES[+m - 1]}/${a}`; };

function descreverRegra(r) {
  const ate = r.fim ? ` até ${rotuloMes(r.fim)}` : '';
  if (r.modo === 'mes') return `só ${rotuloMes(r.inicio)}`;
  if (r.modo === 'ocorrencias') return `${r.ocorrencias} ${r.ocorrencias === 1 ? 'mês' : 'meses'} a partir de ${rotuloMes(r.inicio)}`;
  if (r.modo === 'meses') return `${r.meses.map(m => MESES[m - 1]).join(', ')} de todo ano, desde ${rotuloMes(r.inicio)}${ate}`;
  return `${r.inicio ? 'a partir de ' + rotuloMes(r.inicio) : 'todos os meses'}${ate}, sem término`.replace(', sem término', r.fim ? '' : ', sem término');
}

function editar(c, o, recarregar) {
  folha(c.nome, async (corpo, fechar) => {
    const valor = h('input', { type: 'text', inputmode: 'decimal', value: c.orcado ? centavosParaCampo(c.orcado) : '', placeholder: '0,00' });
    const modo = h('select', null,
      h('option', { value: 'continuo' }, 'Sem término, a partir de um mês'),
      h('option', { value: 'ocorrencias' }, 'Por um número de meses'),
      h('option', { value: 'meses' }, 'Em meses específicos do ano'),
      h('option', { value: 'mes' }, `Só ${nomeMes(o.mes)} (ajuste)`));
    const inicio = h('input', { type: 'month', value: o.mes });
    const fim = h('input', { type: 'month', value: '' });
    const ocor = h('input', { type: 'number', min: 1, max: 240, value: 3 });
    const caixas = MESES.map((m, i) => ({ m: i + 1, el: h('input', { type: 'checkbox' }) }));
    const blocoMeses = h('div', { class: 'meses-ano' }, caixas.map(x => h('label', null, x.el, h('span', null, MESES[x.m - 1]))));
    const cInicio = campo('A partir de', inicio), cFim = campo('Até (opcional)', fim, 'Deixe vazio para não ter término.'),
      cOcor = campo('Quantos meses seguidos', ocor), cMeses = h('div', { class: 'campo' }, h('span', null, 'Meses do ano'), blocoMeses, h('small', null, 'Repete todo ano nos meses marcados; nos demais vale a regra anterior.'));
    const atualizar = () => {
      const m = modo.value;
      const ver = (el, sim) => { el.style.display = sim ? '' : 'none'; };
      ver(cInicio, m !== 'mes'); ver(cFim, m === 'continuo' || m === 'meses'); ver(cOcor, m === 'ocorrencias'); ver(cMeses, m === 'meses');
    };
    modo.addEventListener('change', atualizar); atualizar();
    corpo.append(h('p', { class: 'dica' }, `Realizado no mês: ${brl(c.realizado)} · previsto: ${brl(c.previsto)}`),
      campo('Valor orçado (R$)', valor), campo('Como aplicar', modo), cInicio, cFim, cOcor, cMeses,
      h('button', { class: 'btn', onclick: acao(async () => {
        const v = valor.value.trim() ? parseValor(valor.value) : 0;
        if (Number.isNaN(v) || v < 0) throw new Error('Valor inválido.');
        const item = { categoria_id: c.id, valor_centavos: v, modo: modo.value };
        if (modo.value === 'mes') item.inicio = o.mes;
        else {
          if (!inicio.value) throw new Error('Informe o mês de início.');
          item.inicio = inicio.value;
          if ((modo.value === 'continuo' || modo.value === 'meses') && fim.value) {
            if (fim.value < inicio.value) throw new Error('O término é anterior ao início.');
            item.fim = fim.value;
          }
          if (modo.value === 'ocorrencias') { item.ocorrencias = +ocor.value; if (!(item.ocorrencias >= 1)) throw new Error('Informe o número de meses.'); }
          if (modo.value === 'meses') { item.meses = caixas.filter(x => x.el.checked).map(x => x.m); if (!item.meses.length) throw new Error('Marque ao menos um mês.'); }
        }
        await PUT_('/api/orcamento', { itens: [item] });
        fechar(); aviso('Orçamento salvo'); recarregar();
      }) }, 'Salvar'));
    // regras já existentes desta categoria
    let regras = [];
    try { regras = await GET(`/api/orcamento/regras?categoria_id=${c.id}`); } catch { /* sem regras */ }
    if (regras.length) corpo.append(h('h3', null, 'Regras desta categoria'),
      regras.map(r => h('div', { class: 'regra' }, h('span', null, `${brl(r.valor_centavos)} · ${descreverRegra(r)}`),
        h('button', { class: 'btn link perigo', onclick: acao(async () => { await DEL(`/api/orcamento?regra_id=${r.id}`); fechar(); aviso('Regra removida'); recarregar(); }) }, 'Remover'))),
      h('p', { class: 'dica' }, 'Em cada mês vale a regra aplicável que começou por último; o ajuste de um mês sempre vence.'));
  });
}

async function preencherMedia(recarregar) {
  const sug = await GET('/api/orcamento/media?meses=3');
  if (!sug.length) return aviso('Ainda não há lançamentos confirmados nos últimos 3 meses.', true);
  if (!(await confirmar(`Definir o valor padrão de ${sug.length} categoria(s) pela média dos últimos 3 meses? Valores já definidos serão substituídos.`, 'Preencher'))) return;
  await PUT_('/api/orcamento', { itens: sug.map(s => ({ categoria_id: s.categoria_id, valor_centavos: s.valor_centavos, mes: null })) });
  aviso('Orçamento preenchido'); recarregar();
}
