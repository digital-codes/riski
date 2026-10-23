<template>

  <p>App Component</p>
  <div class="wrapper">
    <TimeLine :search-data="rawData" />
  </div>
  <div class="wrapper">
    <NetworkView v-if="graph && graph.nodes && graph.nodes.length" :graph="graph" @select="onSelect" />
  </div>
  <DetailPanel :selection="selection" :graph="graph" :is-mobile="isMobile" @close="selection = null" />
  <div class="wrapper">
  <SummaryCard v-if="summary && summary.length > 0" :summary="summary"/>
  </div>
</template>

<script setup>
// Inline Component Definition for minimal setup
// Normally you would move this to ./components/SearchResults.vue
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
import TimeLine from './components/TimeLine.vue'; // Assuming you have this component, or you can inline it similarly if needed.
import SummaryCard from './components/SummaryCard.vue';
import DetailPanel from './components/DetailPanel.vue';
// lazy: keeps echarts (large) out of the main bundle until the graph exists
const NetworkView = defineAsyncComponent(() => import('./components/NetworkView.vue'));
const rawData = ref(null);
const summary = ref(null);
const graph = computed(() => rawData.value?.graph ?? null);
const selection = ref(null);
const isMobile = ref(false);

const onSelect = (sel) => {
  // 3.1: selection opens the detail panel; links (oparlId / PDF) live there
  selection.value = sel;
};

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768;
};

onMounted(async () => {
  console.log('App Component Mounted');
  checkMobile();
  window.addEventListener('resize', checkMobile);
  const data = await import('./assets/sampleData.json'); // Assuming you have this file in the same directory, or you can directly paste the JSON here as a constant.
  rawData.value = data.default;
  summary.value = rawData.value.summary; // Assuming your JSON has a summary field
  console.log('Raw Data:', rawData.value.query); // Check if data is loaded correctly
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

/* Mobile Responsive */
@media (max-width: 768px) {
  .wrapper {
    padding: 12px;
  }
}

</style>
