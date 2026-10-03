// Service worker: casca do app disponível offline (rede primeiro, cache como reserva); /api nunca é guardado.
const CACHE = 'fin-casca-v39';
const CASCA = ['/', '/index.html', '/styles.css', '/manifest.webmanifest', '/js/app.js', '/js/util.js', '/js/form.js', '/js/inicio.js',
  '/js/capturar.js', '/js/lanc.js', '/js/cartoes.js', '/js/fatura-import.js', '/js/mais.js', '/js/orcamento.js', '/js/versao.js', '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('fin-casca-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // Compartilhar imagem para o app (menu "Compartilhar" do Android)
  if (req.method === 'POST' && url.pathname === '/share-target') {
    e.respondWith((async () => {
      try {
        const fd = await req.formData();
        const arq = fd.get('arquivo');
        if (arq && arq.size) {
          const cache = await caches.open('fin-share');
          await cache.put('/shared-file', new Response(arq, { headers: { 'Content-Type': arq.type || 'image/jpeg' } }));
        }
      } catch { /* segue para a tela de captura mesmo assim */ }
      return Response.redirect('/#/capturar', 303);
    })());
    return;
  }

  if (req.method !== 'GET' || url.pathname.startsWith('/api/')) return;

  e.respondWith((async () => {
    try {
      const r = await fetch(req, { cache: 'no-cache' });
      if (r.ok) { const c = await caches.open(CACHE); c.put(req, r.clone()); }
      return r;
    } catch {
      const c = await caches.match(req, { ignoreSearch: true });
      return c || (req.mode === 'navigate' ? caches.match('/index.html') : Response.error());
    }
  })());
});
