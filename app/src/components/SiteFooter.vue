<script setup>
import { instance } from '../instanceStore.js';

const year = new Date().getFullYear();

const links = [
  { path: '/dokumentation', label: 'Dokumentation' },
  { path: '/wissen', label: 'Wissen' },
  { path: '/datenschutz', label: 'Datenschutz' },
  { path: '/impressum', label: 'Impressum' },
];

defineEmits(['navigate']);
</script>

<template>
  <footer class="site-footer">
    <div class="footer-inner">
      <p class="footer-text">
        {{ instance.footer }}
      </p>
      <div class="footer-links">
        <a
          v-for="link in links"
          :key="link.path"
          :href="`#${link.path}`"
          class="footer-link"
          @click="$emit('navigate', link.path)"
        >{{ link.label }}</a>
        <a
          href="https://github.com/digital-codes/riski"
          class="footer-link"
          target="_blank"
          rel="noopener noreferrer"
        >Repository</a>
      </div>
      <p class="footer-copy">© {{ year }} riski</p>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: 40px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}

.footer-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.footer-text {
  margin: 0;
  font-size: 0.85rem;
  color: #6b7280;
  max-width: 60ch;
}

.footer-links {
  display: flex;
  gap: 16px;
}

.footer-link {
  color: #667eea;
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 500;
}

.footer-link:hover {
  text-decoration: underline;
}

.footer-copy {
  margin: 0;
  font-size: 0.8rem;
  color: #9ca3af;
}

@media (max-width: 768px) {
  .footer-inner {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px 12px;
  }
}
</style>
