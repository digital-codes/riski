<template>
  <!-- change: intent-router (design D10) — meeting-centric topic list;
       replaces the LLM summary for answer_mode "list_topics" -->
  <section class="topic-list card">
    <h3 class="card-title">Themen der Sitzung ({{ topics.length }})</h3>
    <ol class="topics">
      <li v-for="topic in topics" :key="topic.id" class="topic">
        <div class="topic-head">
          <span class="topic-number">{{ topic.number ?? '•' }}</span>
          <span class="topic-name">{{ topic.name }}</span>
          <span v-if="topic.result" class="topic-result">{{ topic.result }}</span>
        </div>
        <ul v-if="topic.files.length" class="topic-files">
          <li v-for="file in topic.files" :key="file.id">
            <button class="topic-file" type="button" @click="selectFile(file)">
              📄 {{ file.name }}
            </button>
          </li>
        </ul>
      </li>
    </ol>
  </section>
</template>

<script setup>
defineProps({
  topics: { type: Array, default: () => [] },
});

const emit = defineEmits(['select']);

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
</style>
