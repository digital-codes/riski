import { ref, onMounted, onUnmounted } from 'vue';

// hash-based routes; default is home
export const ROUTES = ['/', '/work', '/dokumentation', '/wissen', '/datenschutz', '/impressum'];

const current = ref('/');

function normalize(hash) {
  const path = (hash || '').replace(/^#/, '');
  return ROUTES.includes(path) ? path : '/';
}

function onHashChange() {
  current.value = normalize(window.location.hash);
}

export function useHashRoute() {
  onMounted(() => {
    onHashChange();
    window.addEventListener('hashchange', onHashChange);
  });
  onUnmounted(() => window.removeEventListener('hashchange', onHashChange));

  const navigate = (path) => {
    window.location.hash = `#${ROUTES.includes(path) ? path : '/'}`;
    // scroll to top on page change — a normal scrolling document keeps
    // its scroll position otherwise
    window.scrollTo(0, 0);
  };

  return { route: current, navigate };
}
