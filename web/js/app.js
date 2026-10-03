import { h, api, GET, POST, aviso, limpar, acao, campo } from './util.js';
import { estado, carregarCadastros } from './form.js';
import { inicio } from './inicio.js';
import { capturar } from './capturar.js';
import { lancamentos, novo } from './lanc.js';
import { cartoes } from './cartoes.js';
import { mais, telaInvestimentos } from './mais.js';
import { orcamento } from './orcamento.js';
import { VERSAO_APP } from './versao.js';

const app = document.getElementById('app');
let pedido = 0;

const ABAS = [['inicio', '🏠', 'Início'], ['lancamentos', '🧾', 'Lançamentos'], ['capturar', '📷', 'Capturar'], ['cartoes', '💳', 'Cartões'], ['investimentos', '📈', 'Investimentos']];

function nomeDispositivo() {
  const ua = navigator.userAgent;
  const so = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : 'Dispositivo';
  const nav = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'navegador';
  return `${so} · ${nav}`;
}

// ---------- login por código ----------
function telaLogin(emailInicial = '') {
  limpar(app);
  document.body.classList.add('deslogado');
  const msg = h('p', { class: 'erro-form', hidden: true });
  const caixa = h('main', { class: 'login' });
  app.append(caixa);
  const erro = (e) => { msg.textContent = e.message; msg.hidden = false; };

  function passoEmail() {
    const email = h('input', { type: 'email', required: true, autocomplete: 'email', inputmode: 'email', placeholder: 'voce@exemplo.com', value: emailInicial });
    const btn = h('button', { class: 'btn', type: 'submit' }, 'Receber código');
    limpar(caixa).append(h('div', { class: 'logo' }, '💰'), h('h1', null, 'Finanças'), h('p', { class: 'dica centro' }, 'Entre com seu e-mail. Enviaremos um código de 6 dígitos; sem senha.'),
      h('form', { class: 'form', onsubmit: async (e) => {
        e.preventDefault(); msg.hidden = true; btn.disabled = true;
        try { await api('POST', '/api/auth/solicitar', { email: email.value.trim() }, { semSessao: true }); passoCodigo(email.value.trim()); }
        catch (err) { erro(err); } finally { btn.disabled = false; }
      } }, campo('E-mail', email), msg, btn), h("p", { class: "dica centro" }, `v${VERSAO_APP}`));
    email.focus();
  }
  function passoCodigo(email) {
    const codigo = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 6, pattern: '[0-9]{6}', class: 'codigo', placeholder: '••••••', required: true });
    const btn = h('button', { class: 'btn', type: 'submit' }, 'Entrar');
    const enviar = async () => {
      msg.hidden = true; btn.disabled = true;
      try {
        await api('POST', '/api/auth/verificar', { email, codigo: codigo.value.trim(), dispositivo: nomeDispositivo() }, { semSessao: true });
        await iniciar();
      } catch (err) { erro(err); codigo.select(); } finally { btn.disabled = false; }
    };
    codigo.addEventListener('input', () => { codigo.value = codigo.value.replace(/\D/g, ''); if (codigo.value.length === 6) enviar(); });
    limpar(caixa).append(h('div', { class: 'logo' }, '✉️'), h('h1', null, 'Digite o código'),
      h('p', { class: 'dica centro' }, `Se ${email} puder acessar, enviamos um código. Vale por 10 minutos. Confira também o spam.`),
      h('form', { class: 'form', onsubmit: (e) => { e.preventDefault(); enviar(); } }, campo('Código', codigo), msg, btn),
      h('button', { class: 'btn link', onclick: passoEmail }, 'Usar outro e-mail / pedir novo código'),
      h('p', { class: 'dica centro' }, 'Este aparelho ficará conectado. Você pode revogá-lo em Mais › Dispositivos.'));
    codigo.focus();
  }
  passoEmail();
}

// ---------- casca do app ----------
function montarCasca() {
  document.body.classList.remove('deslogado');
  limpar(app).append(h('main', { id: 'tela', class: 'tela' }),
    h('nav', { class: 'abas', 'aria-label': 'Principal' }, ABAS.map(([id, ic, rot]) => h('a', { href: `#/${id === 'inicio' ? '' : id}`, 'data-aba': id, class: id === 'capturar' ? 'central' : '' }, h('span', { class: 'ic' }, ic), h('span', null, rot)))));
}

const ROTAS = { inicio, capturar, lancamentos, novo, cartoes, mais, orcamento, investimentos: telaInvestimentos };

async function rotear() {
  if (!estado.eu) return;
  const partes = location.hash.replace(/^#\/?/, '').split('?')[0].split('/').filter(Boolean);
  const rota = partes[0] || 'inicio', sub = partes[1];
  const nome = ROTAS[rota] ? rota : 'inicio';
  const tela = document.getElementById('tela');
  if (!tela) return;
  const meu = ++pedido;
  const aba = nome === 'novo' ? 'lancamentos' : nome === 'orcamento' ? 'mais' : nome;
  document.querySelectorAll('.abas a').forEach(a => a.classList.toggle('ativa', a.dataset.aba === aba));
  limpar(tela).append(h('div', { class: 'spinner' }));
  window.scrollTo(0, 0);
  try {
    if (nome !== 'cartoes' && nome !== 'mais') await carregarCadastros();
    const alvo = h('div');
    await ROTAS[nome](alvo, {}, sub);
    if (meu === pedido) {
      limpar(tela).append(alvo);
      // atalho para "Mais" no canto superior direito de todas as telas, menos nas do próprio Mais (e no formulário de novo lançamento)
      if (!['mais', 'orcamento', 'novo'].includes(nome)) tela.append(h('a', { href: '#/mais', class: 'mais-topo', 'aria-label': 'Mais' }, '☰'));
    }
  } catch (e) {
    if (meu === pedido) limpar(tela).append(h('p', { class: 'erro-form' }, e.message), h('button', { class: 'btn sec', onclick: rotear }, 'Tentar de novo'));
  }
}

async function iniciar() {
  try {
    estado.eu = await api('GET', '/api/eu', undefined, { semSessao: true });
  } catch (e) {
    if (e.status === 401) return telaLogin();
    limpar(app).append(h('main', { class: 'login' }, h('p', { class: 'erro-form' }, e.message), h('button', { class: 'btn', onclick: () => location.reload() }, 'Tentar de novo')));
    return;
  }
  try { await carregarCadastros(); } catch (e) { aviso(e.message, true); }
  montarCasca();
  rotear();
}

window.addEventListener('hashchange', rotear);
window.addEventListener('sessao-expirada', () => { estado.eu = null; telaLogin(); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
iniciar();
