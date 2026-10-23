<template>
  <div class="card geo-card">
    <h3 class="card-title">Karte</h3>
    <div ref="mapEl" class="map" role="application" aria-label="Karte der im Suchergebnis genannten Straßen und Stadtteile"></div>
  </div>
</template>

<script setup>
// Adapted from klimaDashboard's SimpleMap.vue (Leaflet + GeoJSON popups).
// Our /geo endpoint serves WGS84 GeoJSON (spike 1.1), so no reprojection
// is needed; streets arrive as LineStrings, districts as Polygons.
import { onMounted, onUnmounted, ref } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import { geoUrl } from '../api.js';

const props = defineProps({
  sessionId: { type: String, required: true },
});

const mapEl = ref(null);
let map = null;
let resizeObserver = null;

const STYLES = {
  street: { color: '#667eea', weight: 5, opacity: 0.85 },
  district: { color: '#764ba2', weight: 2, fillOpacity: 0.15 },
};

onMounted(async () => {
  delete L.Icon.Default.prototype._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: markerIcon2x,
    iconUrl: markerIcon,
    shadowUrl: markerShadow,
  });

  map = L.map(mapEl.value).setView([49.0069, 8.4037], 12); // Karlsruhe
  L.tileLayer('https://sgx.geodatenzentrum.de/wmts_basemapde/tile/1.0.0/de_basemapde_web_raster_farbe/default/GLOBAL_WEBMERCATOR/{z}/{y}/{x}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.bkg.bund.de" target="_blank">GeoBasis-DE/BKG</a> | <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank">CC BY 4.0</a> | © OpenStreetMap contributors',
  }).addTo(map);

  try {
    const res = await fetch(geoUrl(props.sessionId));
    if (!res.ok) return;
    const fc = await res.json();
    if (!fc.features?.length) return;

    const layer = L.geoJSON(fc, {
      style: (f) => STYLES[f.properties?.type] || STYLES.street,
      onEachFeature: (feature, l) => {
        const p = feature.properties || {};
        const items = (p.agendaItems || []).map((k) =>
          `<a href="https://web1.karlsruhe.de/oparl/bodies/0001/agendaitems/${k}" target="_blank" rel="noopener">${k}</a>`).join(', ');
        l.bindPopup(
          `<b>${p.name || ''}</b><br>` +
          `<em>${p.type === 'district' ? 'Stadtteil' : 'Straße'}</em><br>` +
          (items ? `TOPs: ${items}` : '')
        );
      },
    }).addTo(map);

    map.fitBounds(layer.getBounds(), { padding: [24, 24] });
  } catch (e) {
    console.warn('Karte konnte nicht geladen werden:', e);
  }

  resizeObserver = new ResizeObserver(() => map && map.invalidateSize());
  resizeObserver.observe(mapEl.value);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  if (map) map.remove();
  map = null;
});
</script>

<style scoped>
.geo-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 24px;
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.card-title {
  margin: 0 0 12px 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  border-bottom: 2px solid #667eea;
  padding-bottom: 8px;
}

.map {
  width: 100%;
  height: 480px;
  border-radius: 8px;
  z-index: 0;
}

@media (max-width: 768px) {
  .geo-card {
    padding: 16px;
  }
  .map {
    height: 320px;
  }
}
</style>
