<template>
  <div v-if="graph && graph.nodes && graph.nodes.length" class="card network-card">
    <h3 class="card-title">Netzwerk ({{ visibleNodes.length }} Knoten, {{ visibleEdges.length }} Kanten)</h3>

    <div class="filters">
      <div class="filter-row">
        <span class="filter-label">Typen:</span>
        <button v-for="t in allTypes" :key="t" type="button"
                class="chip" :class="{ off: !enabledTypes.has(t) }"
                :style="enabledTypes.has(t) ? { borderColor: typeColor(t) } : {}"
                @click="toggleType(t)">
          <span class="dot" :style="{ background: typeColor(t) }"></span>
          {{ typeLabel(t) }}
        </button>
      </div>
      <div class="filter-row" v-if="allRelations.length > 1">
        <span class="filter-label">Kanten:</span>
        <button v-for="r in allRelations" :key="r" type="button"
                class="chip" :class="{ off: !enabledRelations.has(r) }"
                @click="toggleRelation(r)">
          {{ relationLabel(r) }}
        </button>
      </div>
    </div>

    <div ref="chartEl" class="chart" role="img" aria-label="Netzwerkgraph des Suchergebnisses"></div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import { LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([GraphChart, LegendComponent, TooltipComponent, CanvasRenderer]);

// on mobile, roam/drag must be off — otherwise the canvas swallows every
// touch and the page cannot be scrolled past the chart
const isMobile = ref(window.innerWidth <= 768);
const onResize = () => {
  isMobile.value = window.innerWidth <= 768;
};

const props = defineProps({
  graph: { type: Object, required: true },
  // change: network-highlighting — answer-list membership + rejection
  // state, passed as plain oparlKey arrays and derived into Sets here
  activeFileKeys: { type: Array, default: () => [] },   // enabled docs of the summary list
  rejectedFileKeys: { type: Array, default: () => [] }, // excluded ∪ summarizer-refused
  activeItemKeys: { type: Array, default: () => [] },   // meeting-view topics
});

const emit = defineEmits(['select']);

// node-type presentation: stable palette + German labels (consistent with TimeLine.vue)
const TYPE_COLORS = {
  File: '#70AD47',
  AuxFile: '#9CCB73',
  Paper: '#4472C4',
  AgendaItem: '#FFC000',
  Meeting: '#9E480E',
  Consultation: '#B0A08F',
  Organization: '#764BA2',
  Person: '#E15759',
};
const TYPE_LABELS = {
  File: 'Datei',
  AuxFile: 'Anlage',
  Paper: 'Dokument',
  AgendaItem: 'TOP',
  Meeting: 'Sitzung',
  Consultation: 'Beratung',
  Organization: 'Organisation',
  Person: 'Person',
};
const typeLabel = (t) => TYPE_LABELS[t] || t;
const typeColor = (t) => TYPE_COLORS[t] || '#999999';
const RELATION_LABELS = {
  auxiliaryFile: 'Anlage', mainFile: 'Hauptdokument', consultation: 'Beratung',
  underDirectionOf: 'Richtung', agendaItem: 'TOP', organization: 'Organisation',
  meeting: 'Sitzung', paper: 'Dokument', subordinatedPaper: 'Unterdrucksache',
};
const relationLabel = (r) => RELATION_LABELS[r] || r;

const MAX_DEGREE_SIZE = 46;
const MIN_DEGREE_SIZE = 14;

// ---- filters (tasks 3.3/3.4): display-only, underlying data stays intact ----
const enabledTypes = ref(new Set());
const enabledRelations = ref(new Set());

const allTypes = computed(() => [...new Set(props.graph.nodes.map((n) => n.type))].sort());
const allRelations = computed(() => [...new Set(props.graph.edges.map((e) => e.relation))].sort());

const toggleType = (t) => {
  const next = new Set(enabledTypes.value);
  next.has(t) ? next.delete(t) : next.add(t);
  enabledTypes.value = next;
};
const toggleRelation = (r) => {
  const next = new Set(enabledRelations.value);
  next.has(r) ? next.delete(r) : next.add(r);
  enabledRelations.value = next;
};

const visibleEdges = computed(() => props.graph.edges.filter((e) => enabledRelations.value.has(e.relation)));
const visibleNodes = computed(() => {
  const connected = new Set();
  for (const e of visibleEdges.value) {
    connected.add(e.source);
    connected.add(e.target);
  }
  // keep seed/search-hit files visible even when their relation is filtered out
  return props.graph.nodes.filter((n) => connected.has(n.id) || (n.type === 'File' && n.attrs?.match));
});

// keep filter sets in sync when data changes (search/expand): ADD new
// types/relations enabled, but preserve the user's manual toggles
watch(
  () => props.graph,
  () => {
    const nextTypes = new Set(enabledTypes.value);
    for (const t of allTypes.value) nextTypes.add(t);
    const nextRels = new Set(enabledRelations.value);
    for (const r of allRelations.value) nextRels.add(r);
    enabledTypes.value = nextTypes;
    enabledRelations.value = nextRels;
  },
  { immediate: true }
);

const categories = computed(() =>
  allTypes.value.map((name) => ({ name, color: typeColor(name) }))
);

const degree = computed(() => {
  const d = {};
  for (const e of visibleEdges.value) {
    d[e.source] = (d[e.source] || 0) + 1;
    d[e.target] = (d[e.target] || 0) + 1;
  }
  return d;
});

// ---- answer-list marking (change: network-highlighting) -------------------
// permissive display semantics: only a clear membership/rejection state
// changes the look; everything else renders as before.
// Accepted (docs/topics of the answer list): DOUBLE ring — an SVG-path
// symbol of two concentric stroke circles over the category-colored disc,
// dark stroke for contrast against every category color and the white
// card. Rejected (excluded/refused): a SINGLE red ring — no dimming, so
// the two states never blur into each other.
const RING_COLOR = '#1f2937';
const REJECTED_COLOR = '#dc2626';
// two concentric circles (r 12 / r 7 in a 24-unit box; the symbol scales
// with symbolSize) — same winding, so both strokes render as rings
const DOUBLE_RING_SYMBOL =
  'path://M0,-12 a12,12 0 1,0 0.0001,0 Z M0,-7 a7,7 0 1,0 0.0001,0 Z';

const activeFiles = computed(() => new Set(props.activeFileKeys));
const rejectedFiles = computed(() => new Set(props.rejectedFileKeys));
const activeItems = computed(() => new Set(props.activeItemKeys));

// node id → status: 'active' (in the answer/topic list) | 'rejected'
// (excluded or refused) | undefined (traversal-only node)
function nodeStatus(n) {
  if (n.type === 'File') {
    // rejection wins: an excluded document must never look active
    if (rejectedFiles.value.has(n.oparlKey)) return 'rejected';
    if (activeFiles.value.has(n.oparlKey)) return 'active';
  }
  if (n.type === 'AgendaItem' && activeItems.value.has(n.oparlKey)) return 'active';
  return undefined;
}

function nodeSymbol(n) {
  return nodeStatus(n) === 'active' ? DOUBLE_RING_SYMBOL : 'circle';
}

function nodeItemStyle(n) {
  const status = nodeStatus(n);
  if (status === 'active') {
    // the path symbol is filled with the category color; the two stroke
    // circles form the double ring
    return { color: typeColor(n.type), borderColor: RING_COLOR, borderWidth: 2 };
  }
  if (status === 'rejected') {
    return { borderColor: REJECTED_COLOR, borderWidth: 2 };
  }
  return undefined;
}

function nodeTooltipSuffix(n) {
  const status = nodeStatus(n);
  if (status === 'rejected') return ' — deaktiviert';
  if (status === 'active') {
    return n.type === 'AgendaItem' ? ' — Themenliste' : ' — Trefferliste';
  }
  return '';
}

const chartEl = ref(null);
let chart = null;
let resizeObserver = null;

function truncate(text, max = 40) {
  if (!text) return '';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function toOption() {
  const catIndex = Object.fromEntries(categories.value.map((c, i) => [c.name, i]));
  const visibleIds = new Set(visibleNodes.value.map((n) => n.id));
  // cap label clutter: only label nodes with few connections or high degree
  const maxDeg = Math.max(1, ...Object.values(degree.value));
  const nodes = visibleNodes.value.map((n) => {
    const deg = degree.value[n.id] || 0;
    const itemStyle = nodeItemStyle(n);
    const symbol = nodeSymbol(n);
    const boosted = symbol !== 'circle';
    return {
      id: n.id,
      name: truncate(n.name),
      category: catIndex[n.type] ?? 0,
      symbol,
      symbolSize: (MIN_DEGREE_SIZE + (MAX_DEGREE_SIZE - MIN_DEGREE_SIZE) * Math.sqrt(deg / maxDeg))
        * (boosted ? 1.15 : 1),
      ...(itemStyle ? { itemStyle } : {}),
      // full data for the detail panel — kept raw on the node
      raw: n,
    };
  });
  const links = visibleEdges.value
    .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
    .map((e) => ({
      source: e.source,
      target: e.target,
      relation: e.relation,
      lineStyle: { curveness: 0.15 },
    }));
  return {
  tooltip: {
    formatter: (p) => {
      if (p.dataType === 'edge') {
        return `${p.data.source}<br/>—${p.data.relation}→<br/>${p.data.target}`;
      }
      const raw = p.data.raw || {};
      const lines = [`<b>${raw.type ? typeLabel(raw.type) : ''}</b>`, truncate(raw.name, 60)];
      if (raw.date) lines.push(raw.date);
      if (raw.attrs && raw.attrs.distance != null) lines.push(`Distanz: ${Number(raw.attrs.distance).toFixed(3)}`);
      const suffix = nodeTooltipSuffix(raw);
      if (suffix) lines.push(`<i>${suffix.replace('— ', '')}</i>`);
      return lines.join('<br/>');
    },
  },
    legend: [{ data: categories.value.map((c) => c.name), textStyle: { fontSize: 11 } }],
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: nodes,
        links,
        categories: categories.value,
        roam: !isMobile.value,
        draggable: !isMobile.value,
        label: { show: true, position: 'right', fontSize: 10, formatter: (p) => p.name },
        emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
        force: (() => {
          // change: network-highlighting — fast settling. Larger gravity
          // pulls to the viewport center, friction damps the oscillation,
          // repulsion scales mildly with node count so dense graphs don't
          // clump, and large graphs compute synchronously instead of
          // wobbling into place for seconds.
          const n = nodes.length;
          return {
            repulsion: 320 + Math.min(400, n * 2),
            edgeLength: [60, 160],
            gravity: 0.25,
            friction: 0.35,
            layoutAnimation: n <= 120,
          };
        })(),
      },
    ],
  };
}

function render() {
  if (!chart) return;
  chart.setOption(toOption(), { notMerge: false, lazyUpdate: true });
}

onMounted(() => {
  window.addEventListener('resize', onResize);
  chart = echarts.init(chartEl.value);
  render();
  chart.on('click', (p) => {
    if (p.dataType === 'node') emit('select', { kind: 'node', data: p.data.raw });
    else if (p.dataType === 'edge') emit('select', { kind: 'edge', data: { source: p.data.source, target: p.data.target, relation: p.data.relation } });
  });
  // Deterministic wheel zoom: ECharts' built-in roam handler leaks wheel
  // events to the page when the cursor is over an item (page scrolls,
  // Ctrl+wheel zooms the browser). Capture-phase handler intercepts every
  // wheel event before zrender and dispatches the zoom explicitly.
  chartEl.value.addEventListener('wheel', onWheel, { passive: false, capture: true });
  resizeObserver = new ResizeObserver(() => chart && chart.resize());
  resizeObserver.observe(chartEl.value);
});

function onWheel(e) {
  if (isMobile.value) return; // mobile: one-finger scroll must stay page scroll
  e.preventDefault();
  e.stopPropagation();
  if (!chart) return;
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  chart.dispatchAction({
    type: 'graphRoam',
    seriesIndex: 0,
    zoom: factor,
    originX: e.offsetX,
    originY: e.offsetY,
  });
}

onUnmounted(() => {
  window.removeEventListener('resize', onResize);
  chartEl.value?.removeEventListener('wheel', onWheel, { capture: true });
  if (resizeObserver) resizeObserver.disconnect();
  if (chart) chart.dispose();
  chart = null;
});

// re-render when the roam mode flips (rotation across the breakpoint)
watch(isMobile, () => render());

// re-render when the answer-list marking changes (toggle/refine) — the
// sets are replaced wholesale in App.vue, so plain reference watches work
watch([() => props.activeFileKeys, () => props.rejectedFileKeys,
       () => props.activeItemKeys], () => render());

watch(() => props.graph, render, { deep: true });
</script>

<style scoped>
.network-card {
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

.legend {
  display: none; /* replaced by the filter chips */
}

.filters {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.filter-label {
  font-size: 0.72rem;
  color: #6b7280;
  text-transform: uppercase;
  min-width: 52px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1.5px solid #e5e7eb;
  background: #f9fafb;
  color: #374151;
  border-radius: 14px;
  padding: 3px 10px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.chip:hover { border-color: #667eea; }

.chip.off {
  opacity: 0.45;
  background: #f3f4f6;
}

.chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.chart {
  width: 100%;
  height: 560px;
}

@media (max-width: 768px) {
  .network-card {
    padding: 16px;
  }
  /* let vertical swipes scroll the page instead of being eaten by the canvas */
  .chart {
    height: 380px;
    touch-action: pan-y;
  }
  .network-card .filter-row .filter-label {
    min-width: auto;
  }
}

/* print: the ECharts canvas keeps its screen pixel size and would run past
   the printable page width — scale it into the pane instead */
@media print {
  .network-card {
    break-inside: avoid;
    overflow: hidden;
  }
  .chart {
    height: auto;
  }
  .chart canvas {
    max-width: 100% !important;
    height: auto !important;
  }
  /* interactive-only controls add nothing on paper */
  .network-card .filter-row,
  .network-card .chip {
    display: none;
  }
}
</style>
