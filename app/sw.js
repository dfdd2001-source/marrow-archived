const CACHE_NAME = 'marrow-v7'; // 发版时递增版本号以失效旧缓存
const APP_SHELL = ['./', './index.html', './style.css', './util.mjs', './expr_guard.mjs', './viz.mjs', './app.mjs', './manifest.json'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

// API 请求与代码文件（app.js/index.html）：network-first——拿到新版本就用新的并更新缓存，
// 离线时退回缓存。其余（图标/样式等静态资源）：缓存优先，加快加载。
// cores/*.json 的数据文件同样 network-first：内容更新后用户立即可见。
self.addEventListener('fetch', event => {
  const url = event.request.url;
  const isApiCall = url.includes('/api/');
  const isCode = ['/app.mjs', '/util.mjs', '/expr_guard.mjs', '/viz.mjs', '/index.html', '/style.css', '/cores-index.json'].some(p => url.endsWith(p))
    || url.endsWith('/') || url.includes('/cores/');
  if (isApiCall || isCode) {
    event.respondWith(
      fetch(event.request, { cache: 'reload' })  // 强制回源，绕过 HTTP 启发式缓存
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
