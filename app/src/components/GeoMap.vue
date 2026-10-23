<template>
  <div class="card geo-card">
    <h3 class="card-title">Karte</h3>
    <div ref="mapEl" class="map" role="application" aria-label="Karte der im Suchergebnis genannten Straßen und Stadtteile"></div>
  </div>
</template>

<script setup>
// Adapted from klimaDashboard's SimpleMap.vue (Leaflet + GeoJSON popups).
// The /geo endpoint serves WGS84 GeoJSON (spike 1.1), so no reprojection
// is needed; streets arrive as LineStrings, districts as Polygons.
// The component is a pure renderer: the FeatureCollection comes in as a
// prop (App.vue fetches it — and refetches when the summarizer's relevance
// verdict arrives, so refused documents drop off the map).
import { onMounted, onUnmounted, ref, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

const props = defineProps({
  featureCollection: { type: Object, required: true },
});

const mapEl = ref(null);
let map = null;
let geoLayer = null;
let resizeObserver = null;

const STYLES = {
  street: { color: '#667eea', weight: 5, opacity: 0.85 },
  district: { color: '#764ba2', weight: 2, fillOpacity: 0.15 },
};

function popupHtml(p) {
  const docs = [
    ...(p.fileNames || []).map((n) => `Dokument: ${n}`),
    ...(p.agendaItemNames || []).map((n) => `TOP: ${n}`),
  ];
  return (
    `<b>${p.name || ''}</b><br>` +
    `<em>${p.type === 'district' ? 'Stadtteil' : 'Straße'}</em><br>` +
    (docs.length ? docs.map((d) => `${d}<br>`).join('') : '')
  );
}

function render() {
  if (!map) return;
  if (geoLayer) {
    map.removeLayer(geoLayer);
    geoLayer = null;
  }
  const fc = props.featureCollection;
  if (!fc?.features?.length) return;
  geoLayer = L.geoJSON(fc, {
    style: (f) => STYLES[f.properties?.type] || STYLES.street,
    onEachFeature: (feature, l) => {
      l.bindPopup(popupHtml(feature.properties || {}));
    },
  }).addTo(map);
  map.fitBounds(geoLayer.getBounds(), { padding: [24, 24] });
}

onMounted(() => {
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
  render();
  resizeObserver = new ResizeObserver(() => map && map.invalidateSize());
  resizeObserver.observe(mapEl.value);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  if (map) map.remove();
  map = null;
});

watch(() => props.featureCollection, render, { deep: false });
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
