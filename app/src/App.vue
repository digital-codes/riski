<template>

  <p>App Component</p>
  <div class="wrapper">
    <TimeLine :search-data="rawData" />
  </div>
  <div v-if="summary && summary.length > 0" class="wrapper summary">
    <h2>Summary</h2>
    <div v-html="markdownSummary"></div>
  </div>
</template>

<script setup>
// Inline Component Definition for minimal setup
// Normally you would move this to ./components/SearchResults.vue
import { ref, onMounted, computed } from 'vue';
import TimeLine from './components/TimeLine.vue'; // Assuming you have this component, or you can inline it similarly if needed.

import markdownIt from 'markdown-it';

const md = new markdownIt();
const rawData = ref(null);
const summary = ref(null);
const markdownSummary = computed(() => summary.value ? md.render(summary.value) : '');

onMounted(async () => {
  console.log('App Component Mounted');
  const data = await import('./assets/sampleData.json'); // Assuming you have this file in the same directory, or you can directly paste the JSON here as a constant.
  rawData.value = data.default;
  summary.value = rawData.value.summary; // Assuming your JSON has a summary field
  console.log('Raw Data:', rawData.value.query); // Check if data is loaded correctly
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

/* Mobile Responsive */
@media (max-width: 768px) {
  .wrapper {
    padding: 12px;
  }
}

</style>
