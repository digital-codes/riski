<template>
  <!-- change: intent-router (design D10) — meeting-centric topic list;
       replaces the LLM summary for answer_mode "list_topics".
       change: fix-gremium-session-docs-thread (task 8.2) — each topic got
       a click popup with the topic information (number/name/result/date)
       and the linked document URLs (download) — no graph detail panel
       involved. -->
  <section class="topic-list card">
    <h3 class="card-title">Themen der Sitzung ({{ topics.length }})</h3>
    <ol class="topics">
      <li v-for="topic in topics" :key="topic.id" class="topic">
        <button type="button" class="topic-head" @click="showTopicPopup(topic)">
          <span class="topic-number">{{ topic.number ?? '•' }}</span>
          <span class="topic-name">{{ topic.name }}</span>
          <span v-if="topic.result" class="topic-result">{{ topic.result }}</span>
        </button>
        <div v-if="popupTopic === topic" class="topic-popup">
          <header class="popup-head">
            <span class="popup-title">
              {{ topic.number ? 'TOP ' + topic.number : 'Thema' }}: {{ topic.name }}
            </span>
            <button type="button" class="popup-close" @click="popupTopic = null">✕</button>
          </header>
          <dl class="popup-info">
            <div v-if="topic.result" class="popup-row"><dt>Ergebnis</dt><dd>{{ topic.result }}</dd></div>
            <div v-if="topic.date" class="popup-row"><dt>Sitzung</dt><dd>{{ formatDate(topic.date) }}</dd></div>
            <div v-if="topic.orgs && topic.orgs.length" class="popup-row"><dt>Gremium</dt><dd>{{ topic.orgs.join(', ') }}</dd></div>
            <div class="popup-row"><dt>Dokumente</dt><dd>{{ topic.files.length }}</dd></div>
          </dl>
          <ul v-if="topic.files.length" class="topic-files">
            <li v-for="file in topic.files" :key="file.id">
              <a v-if="file.downloadurl" :href="file.downloadurl" target="_blank" rel="noopener" class="topic-file">
                📄 {{ file.name }}
              </a>
              <span v-else class="topic-file">📄 {{ file.name }}</span>
            </li>
          </ul>
          <p v-else class="popup-none">Keine Sitzungsdokumente zu diesem TOP.</p>
        </div>
        <ul v-else-if="topic.files.length" class="topic-files count-only">
          <li class="count-note">{{ topic.files.length }} Dokument(e) — im Popup der TOP-Zeile</li>
        </ul>
      </li>
    </ol>
  </section>
</template>


<script setup>

const props = defineProps({ topics: { type: Array, default: () => [] } });
const emit = defineEmits(['select']);
import { ref } from 'vue';

const popupTopic = ref(null);
const showTopicPopup = (t) => { popupTopic.value = popupTopic.value === t ? null : t; };
const formatDate = (d) => {
  if (!d) return '';
  try {
    const dt = new Date(d);
    return isNaN(dt) ? String(d) : dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch (e) { return String(d); }
};

// selection payload mirrors NetworkView's node clicks so DetailPanel
// handles both identically (download link for files, calendar page for
// meetings)
const selectFile = (file) => {
  emit('select', {
    kind: 'node',
    data: {
      id: file.id,
      type: 'File',
      oparlKey: file.oparlKey,
      name: file.name,
      date: file.date,
      oparlId: file.oparlId,
      attrs: { downloadurl: file.downloadurl },
    },
  });
};
</script>

<style scoped>
.topic-list {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}

.card-title {
  margin: 0 0 12px;
  font-size: 1rem;
  font-weight: 600;
}

.topics {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.topic {
  border: 1px solid #f3f4f6;
  border-radius: 6px;
  padding: 8px 12px;
}

.topic-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.topic-number {
  flex-shrink: 0;
  min-width: 2em;
  font-weight: 700;
  color: #667eea;
}

.topic-name {
  font-weight: 500;
  word-break: break-word;
}

.topic-result {
  font-size: 0.78rem;
  background: #ecfdf5;
  color: #047857;
  border-radius: 999px;
  padding: 2px 10px;
}

.topic-files {
  list-style: none;
  margin: 6px 0 0;
  padding: 0 0 0 2em;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topic-file {
  background: none;
  border: none;
  padding: 2px 4px;
  font: inherit;
  font-size: 0.88rem;
  color: #2563eb;
  cursor: pointer;
  text-align: left;
}

.topic-file:hover {
  text-decoration: underline;
}
/* change: fix-gremium-session-docs-thread (task 8.2) — topic popup */
.topic-head { all: unset; display: block; cursor: pointer; width: 100%; padding: 4px 6px; border-radius: 6px; }
.topic-head:hover { background: #f1f5f9; }
.topic-popup { margin: .5rem 0 .6rem; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
.popup-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.popup-title { font-weight: 600; color: #1e293b; font-size: .92rem; }
.popup-close { all: unset; cursor: pointer; color: #64748b; padding: 0 .3rem; }
.popup-close:hover { color: #1e293b; }
.popup-info { margin: .4rem 0 .2rem; display: grid; gap: .2rem; }
.popup-info dt { font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; color: #888; display: inline; margin-right: .4rem; }
.popup-info dd { display: inline; margin: 0; font-size: .86rem; color: #334155; }
.popup-none { color: #64748b; font-size: .82rem; margin: .3rem 0 0; }
.count-only .count-note { color: #94a3b8; font-size: .78rem; list-style: none; }

</style>
