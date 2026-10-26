<script setup>
import { onMounted, onUnmounted, ref } from 'vue';
import logo from '../assets/riski-logo.png';

// change: site-menu — the navbar grew beyond a handful of links; a menu
// button (like klimaDashboard's header) scales better than a link row
const links = [
  { path: '/', label: 'Start' },
  { path: '/work', label: 'Das RIS' },
  { path: '/dokumentation', label: 'Dokumentation' },
  { path: '/wissen', label: 'Wissen' },
  { path: '/datenschutz', label: 'Datenschutz' },
  { path: '/impressum', label: 'Impressum' },
];

defineProps({
  route: { type: String, required: true },
});
const emit = defineEmits(['navigate']);

const open = ref(false);
const navEl = ref(null);

function toggle() {
  open.value = !open.value;
}

function go(path) {
  open.value = false;
  emit('navigate', path);
}

function onOutsideClick(e) {
  if (open.value && navEl.value && !navEl.value.contains(e.target)) {
    open.value = false;
  }
}

function onKeydown(e) {
  if (e.key === 'Escape') open.value = false;
}

onMounted(() => {
  document.addEventListener('click', onOutsideClick);
  document.addEventListener('keydown', onKeydown);
});
onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick);
  document.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <nav class="site-nav" ref="navEl">
    <a href="#/" class="nav-brand" @click="go('/')">
      <img :src="logo" alt="riski Logo" class="nav-logo" />
      <span class="nav-title">riski</span>
    </a>
    <button
      type="button"
      class="menu-btn"
      :class="{ open }"
      :aria-expanded="open"
      aria-controls="nav-menu"
      @click="toggle"
    >
      <span class="menu-icon" aria-hidden="true">
        <span></span><span></span><span></span>
      </span>
      Menü
    </button>
    <transition name="menu-fade">
      <div v-if="open" id="nav-menu" class="nav-menu">
        <a
          v-for="link in links"
          :key="link.path"
          :href="`#${link.path}`"
          class="menu-link"
          :class="{ active: route === link.path }"
          :aria-current="route === link.path ? 'page' : undefined"
          @click="go(link.path)"
        >{{ link.label }}</a>
      </div>
    </transition>
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

.menu-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.menu-btn:hover,
.menu-btn.open {
  background: #eef2ff;
  border-color: #667eea;
  color: #667eea;
}

/* hamburger icon */
.menu-icon {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
}

.menu-icon span {
  display: block;
  width: 18px;
  height: 2px;
  border-radius: 2px;
  background: currentColor;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.menu-btn.open .menu-icon span:nth-child(1) {
  transform: translateY(6px) rotate(45deg);
}

.menu-btn.open .menu-icon span:nth-child(2) {
  opacity: 0;
}

.menu-btn.open .menu-icon span:nth-child(3) {
  transform: translateY(-6px) rotate(-45deg);
}

/* dropdown panel */
.nav-menu {
  position: absolute;
  top: 100%;
  right: 24px;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  min-width: 220px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 8px;
  z-index: 110;
}

.menu-link {
  padding: 10px 14px;
  border-radius: 8px;
  text-decoration: none;
  color: #374151;
  font-size: 0.95rem;
  font-weight: 500;
}

.menu-link:hover {
  background: #eef2ff;
  color: #667eea;
}

.menu-link.active {
  background: #667eea;
  color: #fff;
}

.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 768px) {
  .site-nav {
    padding: 10px 12px;
  }

  .nav-logo {
    height: 30px;
  }

  .nav-menu {
    right: 12px;
    left: 12px;
  }
}
</style>
