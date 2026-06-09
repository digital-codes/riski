<template>

  <p>App Component</p>
  <div class="wrapper">
    <TimeLine :search-data="rawData" />
  </div>
</template>

<script setup>
// Inline Component Definition for minimal setup
// Normally you would move this to ./components/SearchResults.vue
import { ref, onMounted } from 'vue';
import TimeLine from './components/TimeLine.vue'; // Assuming you have this component, or you can inline it similarly if needed.

const rawData = ref(null);
onMounted(async () => {
  console.log('App Component Mounted');
  const data = await import('./assets/sampleData.json'); // Assuming you have this file in the same directory, or you can directly paste the JSON here as a constant.
  rawData.value = data.default;
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
</style>
