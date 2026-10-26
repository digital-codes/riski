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
    <RouteInfo
      :intent="intent"
      :applied-filters="appliedFilters"
      :gremium="gremium"
      :fallback-notes="fallbackNotes"
    />
    <div v-if="emptyResponse" class="empty-response">
      <p class="empty-title">{{ emptyResponse.message }}</p>
      <p class="empty-detail">
        Versucht: {{ emptyResponse.intent }}<template v-if="scopeText"> · Scope: {{ scopeText }}</template>
      </p>
    </div>
  </div>
  <div class="wrapper">
    <!-- change: progressive-frontend-rendering — the network view mounts
         only when the graph stage has delivered; until then it shows a
         loading card so the pane sequence (files → timeline → graph) is
         visible -->
    <NetworkView v-if="graph && graph.nodes && graph.nodes.length" :graph="graph"
      :active-file-keys="activeFileKeys"
      :rejected-file-keys="rejectedFileKeys"
      :active-item-keys="activeItemKeys"
      @select="onSelect" />
    <div v-else-if="loadingGraph" class="pane-loading-card">
      <span class="pane-spinner"></span>
      <span>Netzwerk wird aufgebaut…</span>
    </div>
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
    <TopicList
      v-if="topics.length"
      :topics="topics"
      @select="onSelect"
    />
    <SummaryCard v-else-if="summary || summaryLoading" :summary="summary" :loading="summaryLoading && !summary" :mapAvailable="geoAvailable" :files="summaryFiles" :refining="refining" :refined="summaryRefined" @refine="onRefine" @toggle-file="onToggleFile" />
  </div>
  <div class="wrapper">
    <GeoMap v-if="geoAvailable && geoFC" :feature-collection="geoFC" :summary-files="summaryFiles" />
  </div>
  <!-- change: progressive-frontend-rendering — the file list and timeline
       cards fill in as their stages arrive; the wrapper is visible during
       the search so the loading states are shown immediately -->
  <div class="wrapper" v-if="answerMode !== 'list_topics' && (rawData || loadingFiles || loadingTimeline)">
    <TimeLine
      :files="files"
      :files-loading="loadingFiles"
      :timeline="timeline"
      :timeline-loading="loadingTimeline"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
import TimeLine from './TimeLine.vue';
import SummaryCard from './SummaryCard.vue';
import DetailPanel from './DetailPanel.vue';
import RouteInfo from './RouteInfo.vue';
import TopicList from './TopicList.vue';
import { ask as apiAsk, search as apiSearch, summarize as apiSummarize, expand as apiExpand, geoUrl, timeline as apiTimeline, graph as apiGraph } from '../api.js';
// lazy: keeps echarts (large) out of the main bundle until the graph exists
const NetworkView = defineAsyncComponent(() => import('./NetworkView.vue'));
// lazy: keeps leaflet out until a georeferenced result arrives
const GeoMap = defineAsyncComponent(() => import('./GeoMap.vue'));

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
const summaryRefined = ref(false);
// per-session exclusions — applied to every subsequent summarize call
const summaryExclude = ref([]);
// summarizer-refused documents (arrives with the /summarize response)
const summaryRefused = ref([]);
const geoAvailable = ref(false);
const geoFC = ref(null);
const error = ref(null);
const sessionId = ref(null);
// change: intent-router — routing outcome of the last /ask call
const intent = ref(null);
const appliedFilters = ref([]);
const gremium = ref(null);
const fallbackNotes = ref([]);
const emptyResponse = ref(null);
// change: intent-router (D10) — meeting-centric answers: topics replace
// the LLM summary, no map
const topics = ref([]);
const answerMode = ref(null);

// graph is mutable state: search replaces it, /expand merges into it
const graph = ref(null);

// change: progressive-frontend-rendering — per-stage state: the file list
// arrives with the stage-1 response, the timeline with stage 2, the graph
// last; each pane shows its own loading state until then
const files = ref([]);
const timeline = ref([]);
const loadingFiles = ref(false);
const loadingTimeline = ref(false);
const loadingGraph = ref(false);
// monotonically increasing token — responses from a superseded search are
// dropped instead of overwriting the newer search's panes
let searchToken = 0;

// change: network-highlighting — answer-list membership/rejection in the
// network view, derived from the live summary state (updates on every
// toggle/refine without a new search)
const activeFileKeys = computed(() =>
  (summaryFiles.value || [])
    .filter((f) => f.oparlKey && !f.excluded)
    .map((f) => f.oparlKey));
const rejectedFileKeys = computed(() => [...new Set([
  ...summaryExclude.value,
  ...summaryRefused.value,
])]);
const activeItemKeys = computed(() =>
  (topics.value || []).map((t) => t.oparlKey).filter(Boolean));

const onSelect = (sel) => {
  // 3.1: selection opens the detail panel; links (oparlId / PDF) live there
  selection.value = sel;
};

async function runSearch() {
  const q = query.value.trim();
  if (!q || loading.value) return;
  const token = ++searchToken;
  loading.value = true;
  error.value = null;
  // clear all panes immediately — no stale data while the new search runs
  rawData.value = null;
  graph.value = null;
  files.value = [];
  timeline.value = [];
  loadingFiles.value = true;
  loadingTimeline.value = true;
  loadingGraph.value = true;
  summary.value = null;
  summaryLoading.value = false;
  summaryFiles.value = [];
  refining.value = false;
  summaryRefined.value = false;
  summaryExclude.value = [];
  summaryRefused.value = [];
  geoAvailable.value = false;
  geoFC.value = null;
  selection.value = null;
  intent.value = null;
  appliedFilters.value = [];
  gremium.value = null;
  fallbackNotes.value = [];
  emptyResponse.value = null;
  topics.value = [];
  answerMode.value = null;
  try {
    // stage 1: /ask routes the query (intent + filters) and runs recall —
    // the file list renders as soon as this returns, timeline and graph
    // follow via the staged endpoints (change: progressive-frontend-
    // rendering)
    const result = await apiAsk(q, { sessionId: sessionId.value, topK: 10, summarize: false });
    if (token !== searchToken) return;  // superseded by a newer search
    applyStage1(result);
    loadingFiles.value = false;  // stage-1 delivered the file list
    // design D10: meeting-centric answers show the topic list instead of
    // the LLM summary — skip the async summarize round-trip entirely
    if (result.sessionId && answerMode.value !== 'list_topics') {
      summaryLoading.value = true;
      apiSummarize(result.sessionId)
        .then((res) => {
          if (token !== searchToken) return;
          if (res.summary) summary.value = res.summary;
          summaryFiles.value = res.files || [];
          summaryRefined.value = !!res.refined;
          summaryExclude.value = (res.files || []).filter(f => f.excluded).map(f => f.oparlKey);
          summaryRefused.value = res.refused || summaryRefused.value;
          // the summary narrows the map scope to the selected documents —
          // always refresh (unconditional: geoAvailable may still be unset
          // when the summary wins the race against the graph response)
          fetchGeo(token);
        })
        .catch(() => {
          // summary is optional — but the map scope decision (fallback vs
          // summary) must still be made once the outcome is known
          if (geoAvailable.value) fetchGeo(token);
        })
        .finally(() => { summaryLoading.value = false; });
    }
    loading.value = false;
    // stage 2: timeline. Meeting-centric answers hide the timeline card —
    // skip the fetch entirely.
    if (answerMode.value === 'list_topics') {
      loadingTimeline.value = false;
    } else {
      fetchTimeline(result.sessionId, token);
    }
    // stage 3: graph (also carries geo availability — the map is fetched
    // after the graph, its scope is the graph-connected answer set)
    fetchGraph(result.sessionId, token);
  } catch (e) {
    error.value = `Suche fehlgeschlagen (${e.message}). Läuft der API-Server? (uvicorn src.apiServer:app --port 8000)`;
    loading.value = false;
    loadingFiles.value = false;
    loadingTimeline.value = false;
    loadingGraph.value = false;
  }
}

// change: progressive-frontend-rendering — stage 2/3 follow-ups. A failed
// stage logs a warning and clears only its own loading flag, so no pane is
// stuck spinning.
async function fetchTimeline(sid, token) {
  try {
    const res = await apiTimeline(sid);
    if (token !== searchToken) return;
    timeline.value = res.timeline || [];
  } catch (e) {
    console.warn(`Zeitachse konnte nicht geladen werden (${e.message})`);
  } finally {
    if (token === searchToken) loadingTimeline.value = false;
  }
}

async function fetchGraph(sid, token) {
  try {
    const res = await apiGraph(sid);
    if (token !== searchToken) return;
    applyGraph(res);
  } catch (e) {
    console.warn(`Netzwerk konnte nicht geladen werden (${e.message})`);
    if (token === searchToken) loadingGraph.value = false;
  }
}

// change: summary-refine-file-control — user actions re-run the summarizer
// with full content; the current summary stays visible until the new one
// replaces it
// change: summary-refine-file-control — user actions re-run the summarizer
// with full content; the current summary stays visible until the new one
// replaces it. The exclusion set sent here is authoritative (replace
// semantics server-side), so one run per click is enough — unless a toggle
// happens while a refine is in flight: the request would carry a stale
// set (lost update), so a set change is re-sent after the in-flight run.
let lastSentExclude = null;
let resummarizeQueued = false;
let queuedExclude = null;
async function runSummarize({ refine = false, exclude = [] } = {}) {
  if (!sessionId.value) return;
  if (refining.value) {
    // a run is in flight — remember that the exclusion set changed under
    // it and re-send the CURRENT set when the run finishes
    if (JSON.stringify(exclude) !== JSON.stringify(lastSentExclude)) {
      resummarizeQueued = true;
      queuedExclude = [...exclude];
    }
    return;
  }
  refining.value = true;
  lastSentExclude = [...exclude];
  try {
    const res = await apiSummarize(sessionId.value, { refine, exclude });
    if (res.in_progress) {
      // another refine owns the session — but the exclusion set was
      // already updated server-side, so the map must still catch up
      if (geoAvailable.value) fetchGeo();
      return;
    }
    if (res.summary) summary.value = res.summary;
    if (resummarizeQueued) {
      // a toggle happened while this refine ran: the user's newer local
      // state stays authoritative — do not let the (stale) response
      // revert it; the queued re-send below applies it server-side
      summaryFiles.value = (res.files || []).map(f => ({
        ...f, excluded: summaryExclude.value.includes(f.oparlKey),
      }));
    } else {
      summaryFiles.value = res.files || [];
      summaryExclude.value = (res.files || []).filter(f => f.excluded).map(f => f.oparlKey);
    }
    summaryRefined.value = !!res.refined;
    summaryRefused.value = res.refused || summaryRefused.value;
    if (geoAvailable.value) fetchGeo();
  } catch (e) {
    // the exclusion set was already recorded server-side (request-time),
    // so the map must refetch even when the refine itself failed —
    // otherwise deselected documents linger on the map
    if (geoAvailable.value) fetchGeo();
  } finally {
    refining.value = false;
    if (resummarizeQueued && sessionId.value) {
      resummarizeQueued = false;
      const exclude = queuedExclude || summaryExclude.value;
      queuedExclude = null;
      runSummarize({ refine: true, exclude });
    }
  }
}

const onRefine = () => runSummarize({ refine: true, exclude: summaryExclude.value });

// change: intent-router — human-readable tried-scope for the empty state
const scopeText = computed(() => {
  const parts = [];
  if (gremium.value?.orgs?.length) parts.push(gremium.value.orgs.join(', '));
  for (const f of appliedFilters.value) {
    if (f.facet === 'tag' && f.values?.length) parts.push(`Typ ${f.values.join('/')}`);
    if (f.facet === 'organization' && !gremium.value?.orgs?.length && f.values?.length)
      parts.push(f.values.join(', '));
  }
  return parts.join(', ');
});

const onToggleFile = ({ oparlKey, excluded }) => {
  const current = new Set(summaryExclude.value);
  if (excluded) current.add(oparlKey); else current.delete(oparlKey);
  summaryExclude.value = [...current];
  // immediate verdict feedback — the label must not wait for the slow
  // full-content re-run (user finding: label out of sync with the toggle)
  summaryFiles.value = summaryFiles.value.map(f =>
    f.oparlKey === oparlKey ? { ...f, excluded } : f);
  runSummarize({ refine: true, exclude: summaryExclude.value });
};

// change: progressive-frontend-rendering — stage-1 applier: intent fields,
// facets, file list. Timeline and graph fill in later (applyTimeline /
// applyGraph); geo availability only becomes known with the graph stage.
function applyStage1(result) {
  rawData.value = result;
  summary.value = result.summary || null;
  files.value = result.top_files || [];
  sessionId.value = result.sessionId || sessionId.value;
  // change: intent-router — routing fields (absent on plain /search)
  intent.value = result.intent || null;
  appliedFilters.value = result.applied_filters || [];
  gremium.value = result.gremium || null;
  fallbackNotes.value = result.fallback_notes || [];
  emptyResponse.value = result.empty_response || null;
  // change: intent-router (D10) — meeting-centric answers
  topics.value = result.topics || [];
  answerMode.value = result.answer_mode || null;
  summaryRefused.value = (result.summary_refused || []).map(r => r.oparlKey).filter(Boolean);
  geoFC.value = null;
  selection.value = null;
  // meeting-mode answers precompute their graph server-side — it arrives
  // with the staged /graph call like any other session
}

// stage-3 applier: graph + geo availability
function applyGraph(res) {
  graph.value = res.graph || { nodes: [], edges: [] };
  loadingGraph.value = false;
  geoAvailable.value = !!res.geo_available && !!sessionId.value;
  // the summary usually arrives after the graph — its .then fetches /geo
  // with the summary-scope (selected documents only). Fetching here too
  // would race: whichever response resolves last wins, and the stale
  // pre-summary payload (agenda-item/aux-file POIs) could overwrite the
  // corrected one (user finding: Rintheim polygon without a document, not
  // going away on deselect). Only fetch when the summary is already done.
  if (geoAvailable.value && !summaryLoading.value) fetchGeo();
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
// arrives (the scope narrows to the selected documents) and after every
// toggle/refine. Two guards prevent stale payloads from winning:
// - the search token (a newer search invalidates in-flight fetches)
// - a per-search sequence number: the LAST ISSUED fetch wins, even when
//   an earlier fetch resolves later (user finding: the pre-summary
//   graph-scope payload overwrote the summary-scope one)
let geoFetchSeq = 0;
async function fetchGeo(token = searchToken) {
  const seq = ++geoFetchSeq;
  try {
    const res = await fetch(geoUrl(sessionId.value));
    if (!res.ok) return;
    const fc = await res.json();
    // assign even when EMPTY: an empty FeatureCollection is a real state
    // (the last geo-bearing document was deselected) — keeping the previous
    // payload here left deselected POIs on the map (user finding)
    if (token === searchToken && seq === geoFetchSeq) geoFC.value = fc;
  } catch { /* map is optional */ }
}

// offline fallback: static sample so the app still renders without the API;
// the sample carries all stages at once (change: progressive-frontend-
// rendering — applies the staged slots directly)
async function loadSampleFallback() {
  try {
    const data = await import('../assets/sampleData.json');
    const result = data.default;
    applyStage1(result);
    loadingFiles.value = false;
    timeline.value = result.timeline || [];
    loadingTimeline.value = false;
    applyGraph({ graph: result.graph, geo_available: result.geo_available });
    error.value = 'API nicht erreichbar — zeige gespeicherten Beispielsatz.';
  } catch (e) {
    error.value = 'Weder API noch Beispieldaten verfügbar.';
    loadingFiles.value = false;
    loadingTimeline.value = false;
    loadingGraph.value = false;
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

/* change: progressive-frontend-rendering — loading card for the network
   view while the graph stage is pending */
.pane-loading-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 32px 24px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  color: #6b7280;
  font-size: 0.9rem;
}

.pane-loading-card .pane-spinner {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: 3px solid #e5e7eb;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* change: intent-router — honest empty state */
.empty-response {
  margin-top: 12px;
  padding: 14px 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
}

.empty-title {
  margin: 0;
  font-weight: 600;
  color: #92400e;
}

.empty-detail {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: #b45309;
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
