// Suba a versão quando trocar ícones/CSS pra forçar o PWA instalado a atualizar.
const CACHE_VERSION = "pataka-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Limpa caches de versões antigas (inclusive do "equipment-log-v1")
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Passthrough — os dados vêm sempre do servidor (Mongo/Cloudinary); o SW só existe pra
// instalabilidade do PWA (igual ao guardiola).
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
