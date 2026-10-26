<script setup>
import { useHashRoute } from './router.js';
import SiteNav from './components/SiteNav.vue';
import SiteFooter from './components/SiteFooter.vue';
import HomePage from './components/HomePage.vue';
import WorkPage from './components/WorkPage.vue';
import DocsPage from './components/DocsPage.vue';
import KnowledgePage from './components/KnowledgePage.vue';
import LegalPage from './components/LegalPage.vue';

const { route, navigate } = useHashRoute();
</script>

<template>
  <div class="site">
    <SiteNav :route="route" @navigate="navigate" />
    <main class="site-content">
      <HomePage v-if="route === '/'" @navigate="navigate" />
      <WorkPage v-else-if="route === '/work'" />
      <DocsPage v-else-if="route === '/dokumentation'" @navigate="navigate" />
      <KnowledgePage v-else-if="route === '/wissen'" @navigate="navigate" />
      <LegalPage v-else :key="route" :page="route" />
    </main>
    <SiteFooter @navigate="navigate" />
  </div>
</template>

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

/* normal scrolling document: shell is a flex column, content grows,
   footer sits after the content (never fixed) */
.site {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.site-content {
  flex: 1;
}
</style>
