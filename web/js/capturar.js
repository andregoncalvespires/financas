import { h, GET, DEL, api, aviso, acao, limpar, vazio, brl, dataCurta } from './util.js';
import { formTransacao, estado } from './form.js';

const MAX_LADO = 1600;

async function reduzir(arquivo) {
  try {
    const bmp = await createImageBitmap(arquivo, { imageOrientation: 'from-image' });
    const esc = Math.min(1, MAX_LADO / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * esc); c.height = Math.round(bmp.height * esc);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.85));
    return blob || arquivo;
  } catch { return arquivo; } // ex.: formato que o navegador não decodifica: o servidor tenta
}

export async function capturar(raiz, ctx) {
  const area = h('div');
  const lista = h('div');
  const entrada = (capture) => h('input', { type: 'file', accept: 'image/*', capture, hidden: true, onchange: (e) => { if (e.target.files[0]) enviar(e.target.files[0]); e.target.value = ''; } });
  const camera = entrada('environment'), galeria = entrada(null);
  limpar(raiz).append(h('h1', null, 'Capturar'),
    h('p', { class: 'dica' }, estado.eu.ia && estado.eu.ia.modo === 'nenhum'
      ? 'A leitura por IA não está ativa para você. Você pode fotografar mesmo assim: a foto fica guardada como comprovante e você preenche o lançamento à mão. Para ativar a leitura, peça ao administrador ou cadastre a sua chave em ☰ › Meu perfil.'
      : 'Fotografe a nota, o comprovante ou um print de notificação. A IA lê e propõe o lançamento; você só confere.'),
    h('div', { class: 'linha-botoes' },
      h('button', { class: 'btn grande-btn', onclick: () => camera.click() }, '📷 Fotografar'),
      h('button', { class: 'btn sec grande-btn', onclick: () => galeria.click() }, '🖼️ Da galeria')),
    camera, galeria, area, h('h2', null, 'Aguardando conferência'), lista);

  async function recarregarLista() {
    const [pend, erros] = await Promise.all([GET('/api/capturas?status=pendente'), GET('/api/capturas?status=erro')]);
    const todas = [...pend, ...erros].sort((a, b) => b.criado_em.localeCompare(a.criado_em));
    limpar(lista);
    if (!todas.length) return lista.append(vazio('Nada pendente.'));
    for (const c of todas) {
      const s = c.sugestao || {};
      lista.append(h('button', { class: 'linha item', onclick: () => abrir(c) },
        h('img', { class: 'mini', src: `/api/anexos/${c.anexo_id}`, alt: '', loading: 'lazy' }),
        h('div', { class: 'corpo' }, h('b', null, c.status === 'erro' ? ((c.erro || '').includes('não ativa') ? 'Foto guardada' : 'Não consegui ler') : (s.favorecido_nome || s.descricao || 'Comprovante')),
          h('small', null, c.status === 'erro' ? 'toque para lançar manualmente' : `${dataCurta(s.data_competencia || c.criado_em)} · ${(s.alertas || []).length ? '⚠ ' + s.alertas[0] : 'pronto para conferir'}`)),
        c.status === 'erro' ? null : h('b', null, brl(s.valor_centavos))));
    }
  }

  function abrir(c) {
    const s = c.sugestao || {};
    limpar(area).append(h('section', { class: 'cartao' },
      h('img', { class: 'comprovante', src: `/api/anexos/${c.anexo_id}`, alt: 'Comprovante enviado' }),
      c.erro ? h('p', { class: 'erro-form' }, (c.erro || '').includes('não ativa') ? 'Sem leitura por IA: preencha manualmente.' : 'A leitura automática falhou. Preencha manualmente.') : null,
      s.alertas && s.alertas.length ? h('ul', { class: 'alertas' }, s.alertas.map(a => h('li', null, a))) : null,
      s.plastico_rotulo ? h('p', { class: 'dica' }, `Cartão identificado: ${s.plastico_rotulo}`) : null,
      formTransacao({ inicial: s, capturaId: c.id, anexoId: c.anexo_id,
        aoSalvar: async () => { limpar(area); await recarregarLista(); }, aoCancelar: () => limpar(area) }),
      h('button', { class: 'btn link perigo', onclick: acao(async () => { await DEL(`/api/capturas/${c.id}`); limpar(area); aviso('Descartada'); await recarregarLista(); }) }, 'Descartar esta captura')));
    area.scrollIntoView({ behavior: 'smooth' });
  }

  async function enviar(arquivo) {
    limpar(area).append(h('div', { class: 'cartao carregando' }, h('div', { class: 'spinner' }), h('p', null, 'Lendo o comprovante…')));
    try {
      const blob = await reduzir(arquivo);
      const fd = new FormData();
      fd.append('arquivo', blob, 'captura.jpg');
      const cap = await api('POST', '/api/capturas', fd);
      if (cap.status === 'erro' && !(cap.erro || '').includes('não ativa')) aviso('Não consegui ler automaticamente.', true);
      abrir(cap);
      recarregarLista();
    } catch (e) { limpar(area); aviso(e.message, true); }
  }

  // arquivo recebido pelo menu "Compartilhar" do Android (service worker guarda em cache)
  try {
    const cache = await caches.open('fin-share');
    const r = await cache.match('/shared-file');
    if (r) { await cache.delete('/shared-file'); enviar(new File([await r.blob()], 'compartilhado')); }
  } catch { /* sem cache API */ }
  await recarregarLista();
}
