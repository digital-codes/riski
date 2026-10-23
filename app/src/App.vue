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

  <div class="wrapper" v-if="rawData">
    <TimeLine :search-data="rawData" />
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
    <SummaryCard v-if="summary && summary.length > 0" :summary="summary" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
import TimeLine from './components/TimeLine.vue';
import SummaryCard from './components/SummaryCard.vue';
import DetailPanel from './components/DetailPanel.vue';
import { search as apiSearch, expand as apiExpand } from './api.js';
// lazy: keeps echarts (large) out of the main bundle until the graph exists
const NetworkView = defineAsyncComponent(() => import('./components/NetworkView.vue'));

const DEFAULT_QUERY = 'wo liegt die Governance für Digitalisierung bei der Stadt Karlsruhe';

const query = ref(DEFAULT_QUERY);
const rawData = ref(null);
const summary = ref(null);
const selection = ref(null);
const isMobile = ref(false);
const loading = ref(false);
const expanding = ref(false);
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
  try {
    const result = await apiSearch(q, { topK: 10 });
    applyResult(result);
  } catch (e) {
    error.value = `Suche fehlgeschlagen (${e.message}). Läuft der API-Server? (uvicorn src.apiServer:app --port 8000)`;
  } finally {
    loading.value = false;
  }
}

function applyResult(result) {
  rawData.value = result;
  summary.value = result.summary || null;
  graph.value = result.graph || { nodes: [], edges: [] };
  sessionId.value = result.sessionId || null;
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
