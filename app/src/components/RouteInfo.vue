<template>
  <!-- change: intent-router — routing outcome banner; renders nothing
       without intent fields (plain /search responses stay banner-free) -->
  <div v-if="hasIntent" class="route-info">
    <div class="route-row">
      <span class="route-intent">{{ intentLabel }}</span>
      <span v-for="(chip, i) in chips" :key="i" class="route-chip">{{ chip }}</span>
    </div>
    <p v-if="notes.length" class="route-notes">{{ notes.join(' · ') }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  intent: { type: String, default: null },
  appliedFilters: { type: Array, default: () => [] },
  gremium: { type: Object, default: null },
  fallbackNotes: { type: Array, default: () => [] },
});

const INTENT_LABELS = {
  search_topic: 'Themensuche',
  ask_gremium_recent: 'Gremien-Sitzung',
  ask_decision_date: 'Beschlussdatum',
};

const hasIntent = computed(() => !!props.intent);

const intentLabel = computed(() => INTENT_LABELS[props.intent] || props.intent);

const fmtDate = (d) => {
  if (!d) return null;
  try {
    return new Date(d).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return null;
  }
};

const chips = computed(() => {
  const out = [];
  const g = props.gremium;
  if (g && g.orgs?.length) {
    out.push(g.orgs.join(' + '));
    const d = g.meeting ? fmtDate(g.meeting.start_date) : null;
    if (d) out.push(`Sitzung am ${d}`);
  }
  for (const f of props.appliedFilters || []) {
    if (f.facet === 'organization') continue; // already covered by the gremium chip
    if (f.facet === 'tag' && f.values?.length) out.push(`Typ: ${f.values.join(', ')}`);
  }
  return out;
});

const notes = computed(() => props.fallbackNotes || []);
</script>

<style scoped>
.route-info {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
}

.route-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.route-intent {
  font-size: 0.85rem;
  font-weight: 600;
  color: #4338ca;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.route-chip {
  font-size: 0.82rem;
  background: #667eea;
  color: white;
  border-radius: 999px;
  padding: 3px 12px;
  white-space: nowrap;
}

.route-notes {
  margin: 6px 0 0;
  font-size: 0.8rem;
  color: #6b7280;
}
</style>
