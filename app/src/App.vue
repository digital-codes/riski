<template>
  <div class="wrapper">
    <form class="search-bar" @submit.prevent="runSearch">
      <input
        v-model="query"
        class="search-input"
        type="search"
        placeholder="Frage an das Ratsinformationssystem…"
        :disabled="loading"
      />
      <button class="search-btn" type="submit" :disabled="loading || !query.trim()">
        {{ loading ? 'Suche…' : 'Suchen' }}
      </button>
    </form>
    <p v-if="error" class="api-error">{{ error }}</p>
  </div>

  <div class="wrapper" v-if="rawData || loading">
    <header class="query-header">
      <h2>
        {{ (rawData && rawData.query) || query }}
        <span v-if="loading" class="header-spinner" title="Suche läuft…"></span>
      </h2>
    </header>
  </div>
  <div class="wrapper">
    <NetworkView v-if="graph && graph.nodes && graph.nodes.length" :graph="graph" @select="onSelect" />
  </div>
  <DetailPanel
    :selection="selection"
    :graph="graph"
    :is-mobile="isMobile"
    :expanding="expanding"
    @close="selection = null"
    @expand="onExpand"
  />
  <div class="wrapper">
    <SummaryCard v-if="summary || summaryLoading" :summary="summary" :loading="summaryLoading && !summary" :mapAvailable="geoAvailable" :files="summaryFiles" :refining="refining" @refine="onRefine" @toggle-file="onToggleFile" />
  </div>
  <div class="wrapper">
    <GeoMap v-if="geoAvailable && geoFC" :feature-collection="geoFC" />
  </div>
  <div class="wrapper" v-if="rawData">
    <TimeLine :search-data="rawData" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
import TimeLine from './components/TimeLine.vue';
import SummaryCard from './components/SummaryCard.vue';
import DetailPanel from './components/DetailPanel.vue';
import { search as apiSearch, summarize as apiSummarize, expand as apiExpand, geoUrl } from './api.js';
// lazy: keeps echarts (large) out of the main bundle until the graph exists
const NetworkView = defineAsyncComponent(() => import('./components/NetworkView.vue'));
// lazy: keeps leaflet out until a georeferenced result arrives
const GeoMap = defineAsyncComponent(() => import('./components/GeoMap.vue'));

const DEFAULT_QUERY = 'wo liegt die Governance für Digitalisierung bei der Stadt Karlsruhe';

const query = ref(DEFAULT_QUERY);
const rawData = ref(null);
const summary = ref(null);
const selection = ref(null);
const isMobile = ref(false);
const loading = ref(false);
const expanding = ref(false);
const summaryLoading = ref(false);
const summaryFiles = ref([]);
const refining = ref(false);
// per-session exclusions — applied to every subsequent summarize call
const summaryExclude = ref([]);
const geoAvailable = ref(false);
const geoFC = ref(null);
const error = ref(null);
const sessionId = ref(null);

// graph is mutable state: search replaces it, /expand merges into it
const graph = ref(null);

const onSelect = (sel) => {
  // 3.1: selection opens the detail panel; links (oparlId / PDF) live there
  selection.value = sel;
};

async function runSearch() {
  const q = query.value.trim();
  if (!q || loading.value) return;
  loading.value = true;
  error.value = null;
  // clear all panes immediately — no stale data while the new search runs
  rawData.value = null;
  graph.value = null;
  summary.value = null;
  summaryLoading.value = false;
  summaryFiles.value = [];
  refining.value = false;
  summaryExclude.value = [];
  geoAvailable.value = false;
  geoFC.value = null;
  selection.value = null;
  try {
    // render results immediately; the summary arrives asynchronously
    const result = await apiSearch(q, { topK: 10, summarize: false });
    applyResult(result);
    if (result.sessionId) {
      summaryLoading.value = true;
      apiSummarize(result.sessionId)
        .then((res) => {
          if (res.summary) summary.value = res.summary;
          summaryFiles.value = res.files || [];
          summaryExclude.value = (res.files || []).filter(f => f.excluded).map(f => f.oparlKey);
          // the relevance verdict may gate the map — refresh it
          if (geoAvailable.value) fetchGeo();
        })
        .catch(() => { /* summary is optional — ignore failures */ })
        .finally(() => { summaryLoading.value = false; });
    }
  } catch (e) {
    error.value = `Suche fehlgeschlagen (${e.message}). Läuft der API-Server? (uvicorn src.apiServer:app --port 8000)`;
  } finally {
    loading.value = false;
  }
}

// change: summary-refine-file-control — user actions re-run the summarizer
// with full content; the current summary stays visible until the new one
// replaces it
async function runSummarize({ refine = false, exclude = [] } = {}) {
  if (refining.value || !sessionId.value) return;
  refining.value = true;
  try {
    const res = await apiSummarize(sessionId.value, { refine, exclude });
    if (res.summary) summary.value = res.summary;
    summaryFiles.value = res.files || [];
    summaryExclude.value = (res.files || []).filter(f => f.excluded).map(f => f.oparlKey);
    if (geoAvailable.value) fetchGeo();
  } catch (e) { /* keep the previous summary on failure */ }
  finally { refining.value = false; }
}

const onRefine = () => runSummarize({ refine: true, exclude: summaryExclude.value });

const onToggleFile = ({ oparlKey, excluded }) => {
  const current = new Set(summaryExclude.value);
  if (excluded) current.add(oparlKey); else current.delete(oparlKey);
  summaryExclude.value = [...current];
  runSummarize({ refine: true, exclude: summaryExclude.value });
};

function applyResult(result) {
  rawData.value = result;
  summary.value = result.summary || null;
  graph.value = result.graph || { nodes: [], edges: [] };
  sessionId.value = result.sessionId || null;
  geoAvailable.value = !!result.geo_available && !!result.sessionId;
  geoFC.value = null;
  if (geoAvailable.value) fetchGeo();
  selection.value = null;
}

// 2.2: merge /expand response into the current graph, by node id —
// existing nodes/edges are kept (and keep their layout), only new ones append
async function onExpand(nodeId) {
  if (expanding.value) return;
  expanding.value = true;
  error.value = null;
  try {
    const partial = await apiExpand(nodeId);
    const g = graph.value || { nodes: [], edges: [] };
    const nodeIds = new Set(g.nodes.map((n) => n.id));
    const edgeKeys = new Set(g.edges.map((e) => `${e.source}|${e.relation}|${e.target}`));
    const newNodes = partial.nodes.filter((n) => !nodeIds.has(n.id));
    const newEdges = partial.edges.filter((e) => !edgeKeys.has(`${e.source}|${e.relation}|${e.target}`));
    graph.value = {
      nodes: [...g.nodes, ...newNodes],
      edges: [...g.edges, ...newEdges],
    };
  } catch (e) {
    error.value = `Erweiterung fehlgeschlagen (${e.message})`;
  } finally {
    expanding.value = false;
  }
}

// fetch the map FeatureCollection; re-fetched when the summary verdict
// arrives (refused documents are then excluded from the map)
async function fetchGeo() {
  try {
    const res = await fetch(geoUrl(sessionId.value));
    if (!res.ok) return;
    const fc = await res.json();
    if (fc.features?.length) geoFC.value = fc;
  } catch { /* map is optional */ }
}

// offline fallback: static sample so the app still renders without the API
async function loadSampleFallback() {
  try {
    const data = await import('./assets/sampleData.json');
    applyResult(data.default);
    error.value = 'API nicht erreichbar — zeige gespeicherten Beispielsatz.';
  } catch (e) {
    error.value = 'Weder API noch Beispieldaten verfügbar.';
  }
}

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768;
};

onMounted(async () => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  await runSearch();
  if (!rawData.value) await loadSampleFallback();
});

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile);
});
</script>

<style>
* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  background: #f3f4f6;
  color: #1f2937;
}

#app {
  min-height: 100vh;
}

.wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: system-ui, -apple-system, sans-serif;
}

.search-bar {
  display: flex;
  gap: 10px;
}

.search-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 1rem;
  font-family: inherit;
}

.search-input:focus {
  outline: none;
  border-color: #667eea;
}

.search-btn {
  background: #667eea;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.search-btn:disabled {
  background: #c7d2fe;
}

.api-error {
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.88rem;
}

/* Query header (moved from TimeLine.vue — sits above all result panes) */
.query-header {
  margin-bottom: 0;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.query-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  word-break: break-word;
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-spinner {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: 3px solid rgba(255, 255, 255, 0.35);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .query-header h2 {
    font-size: 1rem;
  }
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .wrapper {
    padding: 12px;
  }
  .search-bar {
    flex-direction: column;
  }
}
</style>
