<template>
  <transition name="panel">
    <aside v-if="selection" class="detail-panel" :class="{ mobile: isMobile }">
      <header class="panel-header">
        <span class="type-badge" :style="{ background: typeColor, color: typeTextColor }">{{ typeLabel }}</span>
        <button type="button" class="close-btn" @click="$emit('close')" aria-label="Schließen">✕</button>
      </header>

      <h3 class="panel-title">{{ title }}</h3>

      <dl class="panel-meta">
        <div v-if="date"><dt>Datum</dt><dd>{{ date }}</dd></div>
        <div v-if="subtitle"><dt>Details</dt><dd>{{ subtitle }}</dd></div>
        <div v-if="distance !== undefined && distance !== null"><dt>Relevanz</dt><dd>Distanz {{ Number(distance).toFixed(3) }}</dd></div>
      </dl>

      <div class="panel-actions">
        <a v-if="downloadurl" :href="downloadurl" target="_blank" rel="noopener" class="action-btn primary">
          PDF herunterladen
        </a>
        <a v-if="webUrl" :href="webUrl" target="_blank" rel="noopener" class="action-btn">
          Sitzungskalender öffnen
        </a>
        <a v-if="oparlId" :href="oparlId" target="_blank" rel="noopener" class="action-btn">
          OParl-Datensatz öffnen
        </a>
        <!-- change: disable-organisation-expansion — expansion is
             disabled for types the backend reports as not expandable
             (Organisation for now): the control explains instead of
             failing with "Erweiterung fehlgeschlagen" -->
        <template v-if="node">
          <button type="button" class="action-btn" :disabled="expanding || !nodeExpandable"
                  :title="nodeExpandable ? '' : 'Dieser Knotentyp wird nicht weiter expandiert'"
                  @click="$emit('expand', node.id)">
            {{ expanding ? 'Lade Nachbarn…' : `Nachbarn laden` }}
          </button>
          <p v-if="!nodeExpandable" class="expand-hint">Organisationen werden nicht weiter expandiert.</p>
        </template>
      </div>

      <section v-if="related.length" class="panel-related">
        <h4>Verbundene Entitäten ({{ related.length }})</h4>
        <ul>
          <li v-for="rel in related" :key="rel.label + rel.name">
            <span class="rel-label">{{ rel.label }}</span>
            <a v-if="rel.url" :href="rel.url" target="_blank" rel="noopener">{{ rel.name }}</a>
            <span v-else>{{ rel.name }}</span>
          </li>
        </ul>
      </section>
    </aside>
  </transition>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  selection: { type: Object, default: null }, // {kind: 'node'|'edge', data}
  graph: { type: Object, default: null },
  isMobile: { type: Boolean, default: false },
  expanding: { type: Boolean, default: false },
  // change: disable-organisation-expansion — expandable node types from the
  // graph payload (backend-owned; empty list ⇒ fall back to expandable,
  // matching the staggered-rollout contract in the design)
  expandableTypes: { type: Array, default: () => [] },
});

defineEmits(['close', 'expand']);

const TYPE_LABELS = {
  File: 'Datei', AuxFile: 'Anlage', Paper: 'Dokument', AgendaItem: 'TOP',
  Meeting: 'Sitzung', Consultation: 'Beratung', Organization: 'Organisation', Person: 'Person',
};

const RELATION_LABELS = {
  auxiliaryFile: 'Anlage zu', mainFile: 'Hauptdokument zu',
  consultation: 'Beratung', underDirectionOf: 'unter Leitung von',
  agendaItem: 'Tagesordnungspunkt', organization: 'Organisation',
  meeting: 'Sitzung', paper: 'Dokument', subordinatedPaper: 'Unterdrucksache',
  semanticSimilarity: 'ähnlich wie',
};

const TYPE_COLORS = {
  File: '#70AD47', AuxFile: '#9CCB73', Paper: '#4472C4', AgendaItem: '#FFC000',
  Meeting: '#9E480E', Consultation: '#B0A08F', Organization: '#764BA2', Person: '#E15759',
};

const node = computed(() => (props.selection?.kind === 'node' ? props.selection.data : null));

// change: disable-organisation-expansion — derive the expansion control
// state from the payload's expandable_types (single source of truth);
// without the field (old payload) the button stays enabled
const nodeExpandable = computed(() => {
  if (!node.value) return false;
  if (!props.expandableTypes.length) return true;
  return props.expandableTypes.includes(node.value.type);
});
const edge = computed(() => (props.selection?.kind === 'edge' ? props.selection.data : null));

const raw = computed(() => node.value?.raw || node.value || {});
const typeLabel = computed(() => {
  const base = TYPE_LABELS[raw.value.type] || raw.value.type || 'Kante';
  // change: network-highlighting — agenda items read "Tagesordnungspunkt"
  // (with their TOP number when known), not the abbreviated "TOP"
  if (raw.value.type === 'AgendaItem') {
    const num = raw.value.attrs?.number;
    return num ? `Tagesordnungspunkt (TOP ${num})` : 'Tagesordnungspunkt';
  }
  return base;
});
const typeColor = computed(() => TYPE_COLORS[raw.value.type] || '#667eea');
// white text is unreadable on the light category fills (AgendaItem yellow,
// AuxFile light green) — pick the text color by background luminance
const typeTextColor = computed(() => {
  const hex = typeColor.value.replace('#', '');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  // WCAG relative luminance approximation
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#1f2937' : 'white';
});
const title = computed(() => {
  if (edge.value) return `${edge.value.relation}`;
  return raw.value.name || 'Ohne Titel';
});
const date = computed(() => raw.value.date || null);
const oparlId = computed(() => raw.value.oparlId || null);
const downloadurl = computed(() => raw.value.attrs?.downloadurl || null);
const webUrl = computed(() => raw.value.attrs?.webUrl || null);
const distance = computed(() => raw.value.attrs?.distance);
const subtitle = computed(() => raw.value.attrs?.fileName || raw.value.attrs?.paperType || raw.value.attrs?.reference || null);

// neighbors of the selected node, via the graph's edges
const related = computed(() => {
  if (edge.value || !props.graph) return [];
  const id = raw.value.id;
  const out = [];
  for (const e of props.graph.edges || []) {
    let other = null;
    if (e.source === id) other = e.target;
    else if (e.target === id) other = e.source;
    if (!other) continue;
    const n = (props.graph.nodes || []).find((x) => x.id === other);
    if (!n) continue;
    out.push({
      label: RELATION_LABELS[e.relation] || e.relation,
      name: n.name || n.id,
      // prefer the public calendar page for meetings, PDF for files
      url: n.attrs?.webUrl || n.attrs?.downloadurl || n.oparlId,
    });
  }
  return out;
});
</script>

<style scoped>
.detail-panel {
  position: fixed;
  /* below the sticky navbar (its close button sat behind it) */
  top: 72px;
  right: 16px;
  width: 380px;
  max-height: calc(100vh - 88px);
  overflow-y: auto;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  padding: 16px 20px;
  z-index: 50;
}

.detail-panel.mobile {
  top: auto;
  right: 0;
  bottom: 0;
  left: 0;
  width: 100%;
  max-height: 55vh;
  border-radius: 16px 16px 0 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.type-badge {
  color: white;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 12px;
}

.close-btn {
  background: transparent;
  border: none;
  font-size: 1rem;
  cursor: pointer;
  color: #6b7280;
  padding: 4px 8px;
}
.close-btn:hover { color: #1f2937; }

.panel-title {
  margin: 0 0 10px 0;
  font-size: 1rem;
  color: #1f2937;
  line-height: 1.4;
}

.panel-meta { margin: 0 0 12px 0; }
.panel-meta > div { display: flex; gap: 8px; margin: 4px 0; font-size: 0.85rem; }
.panel-meta dt { color: #6b7280; min-width: 70px; }
.panel-meta dd { margin: 0; color: #1f2937; }

.panel-actions { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.action-btn {
  display: block;
  text-align: center;
  padding: 9px 14px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  color: #374151;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 500;
}
.action-btn:hover { border-color: #667eea; color: #667eea; }
.action-btn.primary { background: #667eea; border-color: #667eea; color: white; }
.action-btn.primary:hover { background: #5a6fd6; color: white; }
.action-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.action-btn:disabled:hover { border-color: #e5e7eb; color: #374151; }
.expand-hint { margin: 2px 0 0; font-size: 0.78rem; color: #6b7280; }

.panel-related h4 {
  margin: 0 0 8px 0;
  font-size: 0.8rem;
  text-transform: uppercase;
  color: #6b7280;
}
.panel-related ul { list-style: none; margin: 0; padding: 0; }
.panel-related li { margin: 6px 0; font-size: 0.85rem; display: flex; gap: 8px; align-items: baseline; }
.rel-label {
  flex-shrink: 0;
  font-size: 0.68rem;
  background: #dbeafe;
  color: #1e40af;
  padding: 1px 7px;
  border-radius: 10px;
}
.panel-related a { color: #667eea; text-decoration: none; word-break: break-word; }
.panel-related a:hover { text-decoration: underline; }

.panel-enter-active, .panel-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.panel-enter-from, .panel-leave-to { opacity: 0; transform: translateX(24px); }
.detail-panel.mobile.panel-enter-from, .detail-panel.mobile.panel-leave-to { transform: translateY(100%); }
</style>
