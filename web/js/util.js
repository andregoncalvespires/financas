// Utilidades: DOM seguro (sem innerHTML), API, formatação, avisos e folhas (bottom sheets).

export function h(tag, attrs, ...filhos) {
  const el = document.createElement(tag);
  // append tolerante: aceita null/false e listas aninhadas (o append nativo imprimiria "null" e "[object ...]")
  el.append = (...f) => anexar(el, f);
  let valor;
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value') valor = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  anexar(el, filhos);
  if (valor !== undefined) el.value = valor; // depois dos filhos, para <select>
  return el;
}

function anexar(el, filhos) {
  for (const f of filhos) {
    if (f == null || f === false) continue;
    if (Array.isArray(f)) anexar(el, f);
    else el.appendChild(f instanceof Node ? f : document.createTextNode(String(f)));
  }
}

export function limpar(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

// ---------- API ----------
export class ApiError extends Error {
  constructor(msg, status) { super(msg); this.status = status; }
}

function textoErro(d, status) {
  const det = d && d.detail;
  if (typeof det === 'string') return det;
  if (Array.isArray(det)) return det.map(e => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join('; ');
  if (status === 413) return 'Arquivo grande demais.';
  if (status === 0) return 'Sem conexão com o servidor.';
  return `Erro ${status}`;
}

export async function api(metodo, caminho, corpo, opts = {}) {
  const init = { method: metodo, credentials: 'same-origin', headers: { 'X-Fin': '1' } };
  if (corpo instanceof FormData) init.body = corpo;
  else if (corpo !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(corpo); }
  let r;
  try { r = await fetch(caminho, init); } catch { throw new ApiError(textoErro(null, 0), 0); }
  let dados = null;
  try { dados = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok) {
    if (r.status === 401 && !opts.semSessao) window.dispatchEvent(new Event('sessao-expirada'));
    throw new ApiError(textoErro(dados, r.status), r.status);
  }
  return dados;
}
export const GET = (c) => api('GET', c);
export const POST = (c, b) => api('POST', c, b === undefined ? {} : b);
export const PATCH = (c, b) => api('PATCH', c, b);
export const PUT_ = (c, b) => api('PUT', c, b);
export const DEL = (c) => api('DELETE', c);

// ---------- formatação ----------
const fmtBRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
export const brl = (c) => fmtBRL.format((c || 0) / 100);

export function parseValor(s) {
  s = String(s || '').replace(/R\$|\s/g, '');
  if (!s) return NaN;
  if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
  const n = Number(s);
  return Number.isFinite(n) ? Math.round(n * 100) : NaN;
}
export const centavosParaCampo = (c) => (Math.abs(c) / 100).toFixed(2).replace('.', ',');

const p2 = (n) => String(n).padStart(2, '0');
export const isoData = (d) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
export const hojeISO = () => isoData(new Date());
export const mesISO = (d = new Date()) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}`;
export function somarMes(mes, n) {
  const [a, m] = mes.split('-').map(Number);
  const d = new Date(a, m - 1 + n, 1);
  return mesISO(d);
}
export function intervaloMes(mes) {
  const [a, m] = mes.split('-').map(Number);
  return [`${a}-${p2(m)}-01`, isoData(new Date(a, m, 0))];
}
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
export const nomeMes = (mes) => { const [a, m] = mes.split('-').map(Number); return `${MESES[m - 1]} de ${a}`; };
export const dataCurta = (iso) => { const [, m, d] = String(iso).slice(0, 10).split('-'); return `${d}/${m}`; };
export const dataLonga = (iso) => { const [a, m, d] = String(iso).slice(0, 10).split('-'); return `${d}/${m}/${a}`; };
const DIAS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
export function rotuloDia(iso) {
  const [a, m, d] = iso.split('-').map(Number);
  const dt = new Date(a, m - 1, d);
  const hoje = hojeISO();
  const ontem = isoData(new Date(Date.now() - 864e5));
  const pre = iso === hoje ? 'Hoje · ' : iso === ontem ? 'Ontem · ' : `${DIAS[dt.getDay()]}, `;
  return `${pre}${p2(d)}/${p2(m)}`;
}

export const FORMAS = {
  boleto: 'Boleto', debito_automatico: 'Débito automático', debito: 'Débito', pix: 'Pix', ted: 'TED/DOC',
  dinheiro: 'Dinheiro', cheque: 'Cheque', cartao: 'Cartão de crédito', outro: 'Outro',
};
export const PAPEIS = { leitor: 'Só consulta', editor: 'Consulta e lança', gestor: 'Gerencia (convida e edita a conta)', dono: 'Dono' };

// ---------- avisos e folhas ----------
let tToast;
export function aviso(msg, erro = false) {
  let t = document.getElementById('toast');
  if (!t) { t = h('div', { id: 'toast', role: 'status' }); document.body.append(t); }
  t.textContent = msg;
  t.className = 'toast ' + (erro ? 'erro' : 'ok') + ' visivel';
  clearTimeout(tToast);
  tToast = setTimeout(() => t.classList.remove('visivel'), erro ? 5000 : 2500);
}

export function folha(titulo, construir) {
  const fundo = h('div', { class: 'fundo' });
  const corpo = h('div', { class: 'folha-corpo' });
  const caixa = h('div', { class: 'folha', role: 'dialog', 'aria-modal': 'true', 'aria-label': titulo },
    h('div', { class: 'folha-topo' }, h('h2', null, titulo), h('button', { class: 'icone', 'aria-label': 'Fechar', onclick: () => fechar() }, '✕')),
    corpo);
  fundo.append(caixa);
  const aoTecla = (e) => { if (e.key === 'Escape') fechar(); };
  function fechar() { document.removeEventListener('keydown', aoTecla); fundo.remove(); document.body.classList.remove('sem-rolagem'); }
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fechar(); });
  document.addEventListener('keydown', aoTecla);
  document.body.append(fundo);
  document.body.classList.add('sem-rolagem');
  construir(corpo, fechar);
  return fechar;
}

export function confirmar(texto, rotulo = 'Confirmar', perigo = false) {
  return new Promise((res) => {
    folha('Confirmar', (corpo, fechar) => {
      corpo.append(h('p', null, texto), h('div', { class: 'linha-botoes' },
        h('button', { class: 'btn sec', onclick: () => { fechar(); res(false); } }, 'Cancelar'),
        h('button', { class: 'btn ' + (perigo ? 'perigo' : ''), onclick: () => { fechar(); res(true); } }, rotulo)));
    });
  });
}

// Pergunta a data em que o dinheiro realmente se moveu (a do extrato). Resolve com 'AAAA-MM-DD' ou null se cancelar.
// Sugere a data prevista quando já passou; se for futura, sugere hoje.
export function dataEfetivacao({ titulo, valor, prevista, rotulo = 'Confirmar' }) {
  return new Promise((res) => {
    const hoje = hojeISO();
    const prev = prevista ? String(prevista).slice(0, 10) : '';
    const campoData = h('input', { type: 'date', value: prev && prev <= hoje ? prev : hoje, max: hoje, required: true });
    folha('Data da efetivação', (corpo, fechar) => {
      corpo.append(
        h('p', null, h('b', null, titulo), valor ? ` · ${valor}` : ''),
        campo('Data em que aconteceu', campoData),
        h('small', { class: 'dica' }, prev ? `Prevista para ${dataLonga(prev)}. Use a data que aparece no extrato do banco.` : 'Use a data que aparece no extrato do banco.'),
        h('div', { class: 'linha-botoes' },
          h('button', { class: 'btn sec', onclick: () => { fechar(); res(null); } }, 'Cancelar'),
          h('button', { class: 'btn', onclick: () => { if (!campoData.value) { campoData.focus(); return; } const d = campoData.value; fechar(); res(d); } }, rotulo)));
    });
  });
}

// botão que desabilita durante a ação assíncrona e mostra o erro
export function acao(fn) {
  return async (e) => {
    const b = e.currentTarget;
    if (b.disabled) return;
    b.disabled = true;
    try { await fn(e); } catch (err) { aviso(err.message || 'Erro', true); } finally { b.disabled = false; }
  };
}

export const campo = (rotulo, entrada, dica) =>
  h('label', { class: 'campo' }, h('span', null, rotulo), entrada, dica ? h('small', null, dica) : null);

export const vazio = (msg) => h('p', { class: 'vazio' }, msg);
