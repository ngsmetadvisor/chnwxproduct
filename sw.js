// Shared across every page in this repo (camera.html, TSRAmap.html, ...).
// Only ONE service worker can be active per scope, so this file — not a
// per-page one — is what every page should register, each just adding its
// own files to FILES below when it needs offline support.
const CACHE = 'chnwxproduct-v15';
const FILES = [
  // camera.html app shell
  './camera.html',
  './manifest.webmanifest',

  // TSRAmap.html app shell
  './TSRAmap.html',
  './manifest-tsramap.webmanifest',
  './tsramap-icon-192.png',
  './tsramap-icon-512.png',
  './tsramap-apple-touch-icon.png',

  // shared icons
  './apple-touch-icon.png',
  './icon-192.png',
  './icon-512.png',

  // TSRAmap vendor libraries
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js',

  // TSRAmap static basemap/data — these rarely change, safe to precache
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_coastline.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces_lines.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_rivers_lake_centerlines.geojson',
  'https://raw.githubusercontent.com/ngsmetadvisor/SfcMap/refs/heads/main/Alberta_Fire_Weather_Forecast_Zones.kml',
  'https://raw.githubusercontent.com/ngsmetadvisor/SfcMap/refs/heads/main/stations.csv',
  'https://raw.githubusercontent.com/ngsmetadvisor/chnwxproduct/refs/heads/main/stationIP.csv'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      // One file per add() call, each wrapped in its own catch, so a single
      // 404/CORS failure (e.g. an icon you haven't uploaded yet) can't sink
      // the whole install the way addAll() would.
      .then(c => Promise.all(FILES.map(f => c.add(f).catch(err => {
        console.warn('[sw] failed to precache', f, err);
      }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network first so radar/alerts/lightning/updates stay live when online;
// falls back to the cached copy when offline. Only successful responses are
// cached, so a transient upstream error never gets baked in and replayed
// later as if it were current data.
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(r => {
        if (r && r.ok) {
          const copy = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return r;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
