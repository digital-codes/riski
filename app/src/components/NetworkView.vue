<template>
  <div v-if="graph && graph.nodes && graph.nodes.length" class="card network-card">
    <h3 class="card-title">Netzwerk ({{ graph.nodes.length }} Knoten, {{ graph.edges.length }} Kanten)</h3>
    <div class="legend">
      <span v-for="cat in categories" :key="cat.name" class="legend-item">
        <span class="dot" :style="{ background: cat.color }"></span>
        {{ typeLabel(cat.name) }}
      </span>
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

const props = defineProps({
  graph: { type: Object, required: true },
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

const MAX_DEGREE_SIZE = 46;
const MIN_DEGREE_SIZE = 14;

const categories = computed(() => {
  const present = [...new Set(props.graph.nodes.map((n) => n.type))].sort();
  return present.map((name) => ({ name, color: TYPE_COLORS[name] || '#999999' }));
});

const degree = computed(() => {
  const d = {};
  for (const e of props.graph.edges) {
    d[e.source] = (d[e.source] || 0) + 1;
    d[e.target] = (d[e.target] || 0) + 1;
  }
  return d;
});

const chartEl = ref(null);
let chart = null;
let resizeObserver = null;

function truncate(text, max = 40) {
  if (!text) return '';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function toOption() {
  const catIndex = Object.fromEntries(categories.value.map((c, i) => [c.name, i]));
  // cap label clutter: only label nodes with few connections or high degree
  const maxDeg = Math.max(1, ...Object.values(degree.value));
  const nodes = props.graph.nodes.map((n) => {
    const deg = degree.value[n.id] || 0;
    return {
      id: n.id,
      name: truncate(n.name),
      category: catIndex[n.type] ?? 0,
      symbolSize: MIN_DEGREE_SIZE + (MAX_DEGREE_SIZE - MIN_DEGREE_SIZE) * Math.sqrt(deg / maxDeg),
      itemStyle: n.attrs && n.attrs.match ? {} : undefined,
      // full data for the detail panel (task 3.x) — kept raw on the node
      raw: n,
    };
  });
  const links = props.graph.edges.map((e) => ({
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
        roam: true,
        draggable: true,
        label: { show: true, position: 'right', fontSize: 10, formatter: (p) => p.name },
        emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
        force: {
          repulsion: 320,
          edgeLength: [60, 160],
          gravity: 0.12,
          layoutAnimation: true,
        },
      },
    ],
  };
}

function render() {
  if (!chart) return;
  chart.setOption(toOption(), { notMerge: false, lazyUpdate: true });
}

onMounted(() => {
  chart = echarts.init(chartEl.value);
  render();
  chart.on('click', (p) => {
    if (p.dataType === 'node') emit('select', { kind: 'node', data: p.data.raw });
    else if (p.dataType === 'edge') emit('select', { kind: 'edge', data: { source: p.data.source, target: p.data.target, relation: p.data.relation } });
  });
  resizeObserver = new ResizeObserver(() => chart && chart.resize());
  resizeObserver.observe(chartEl.value);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  if (chart) chart.dispose();
  chart = null;
});

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
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 0.8rem;
  color: #374151;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 10px;
  height: 10px;
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
  .chart {
    height: 380px;
  }
}
</style>
