const SW_VERSION = "equipment-log-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// Passthrough — só existe pra satisfazer o requisito de instalabilidade do PWA (igual ao guardiola).
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
