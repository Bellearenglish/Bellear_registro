const CACHE_NAME = "bellear-v1";
const urlsToCache = [
  "/",
  "/login",
  "/static/bootstrap.min.css",
  "/static/style.css"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});