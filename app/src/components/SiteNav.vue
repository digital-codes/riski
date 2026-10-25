<script setup>
import logo from '../assets/riski-logo.png';

const links = [
  { path: '/work', label: 'Das RIS' },
  { path: '/datenschutz', label: 'Datenschutz' },
  { path: '/impressum', label: 'Impressum' },
];

defineProps({
  route: { type: String, required: true },
});
defineEmits(['navigate']);
</script>

<template>
  <nav class="site-nav">
    <a href="#/" class="nav-brand" @click="$emit('navigate', '/')">
      <img :src="logo" alt="riski Logo" class="nav-logo" />
      <span class="nav-title">riski</span>
    </a>
    <div class="nav-links">
      <a
        v-for="link in links"
        :key="link.path"
        :href="`#${link.path}`"
        class="nav-link"
        :class="{ active: route === link.path }"
        @click="$emit('navigate', link.path)"
      >{{ link.label }}</a>
    </div>
  </nav>
</template>

<style scoped>
.site-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: #1f2937;
}

.nav-logo {
  height: 36px;
  width: auto;
}

.nav-title {
  font-size: 1.25rem;
  font-weight: 700;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.nav-links {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.nav-link {
  padding: 8px 14px;
  border-radius: 8px;
  text-decoration: none;
  color: #374151;
  font-size: 0.95rem;
  font-weight: 500;
}

.nav-link:hover {
  background: #eef2ff;
  color: #667eea;
}

.nav-link.active {
  background: #667eea;
  color: #fff;
}

@media (max-width: 768px) {
  .site-nav {
    flex-direction: column;
    gap: 8px;
    padding: 10px 12px;
  }

  .nav-logo {
    height: 30px;
  }
}
</style>
