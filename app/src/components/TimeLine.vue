<template>
  <div v-if="searchData" class="search-results-container">
    <!-- Header: Query String -->
    <header class="query-header">
      <h2>{{ query }}</h2>
    </header>

    <!-- Card 1: Files (First 3 visible, rest collapsed) -->
    <section class="card files-card">
      <h3 class="card-title">Dateien ({{ files.length }})</h3>
      
      <div class="files-list">
        <div 
          v-for="(file, index) in files" 
          :key="file.oparlKey"
          class="file-item-wrapper"
          :class="{ 'is-hidden': !isExpanded && index >= 3 }"
        >
          <a 
            :href="file.downloadurl"
            target="_blank"
            class="file-link"
          >
            <div class="file-info">
              <span class="file-name">{{ file.name }}</span>
              <span class="file-meta">{{ formatDate(file.date) }} • {{ file.fileName }}</span>
            </div>
            <button type="button" class="download-btn" @click.stop.prevent="openLink(file.downloadurl)">
              Download PDF
            </button>
          </a>
        </div>

        <!-- Toggle Button -->
        <button 
          v-if="files.length > 3" 
          @click="toggleExpand"
          class="toggle-btn"
        >
          {{ isExpanded ? 'Weniger anzeigen' : `Mehr anzeigen (${files.length - 3})` }}
        </button>
      </div>
    </section>

    <!-- Card 2: Timeline -->
    <section class="card timeline-card">
      <h3 class="card-title">Zeitachse ({{ timeline.length }})</h3>
      
      <div class="timeline-controls">
        <button @click="scrollTimeline(-100)" class="nav-btn left">‹</button>
        <div class="timeline-wrapper" ref="timelineContainer">
          <div class="timeline-scroll-track" ref="timelineTrack">
            <div 
              v-for="(group, idx) in timeline" 
              :key="idx"
              class="timeline-card-item"
            >
              <div class="date-range">
                {{ formatRange(group.start_date, group.end_date) }}
              </div>
              
              <div class="events-list">
                <div 
                  v-for="event in group.events" 
                  :key="event.id"
                  class="event-chip"
                >
                  <span class="tag">{{ formatType(event.type) }}</span>
                  <span class="title">{{ event.name }}</span>
                  <span class="sub-date">{{ formatTime(event.date) }}</span>
                  
                  <a 
                    v-if="event.oparlId"
                    :href="event.oparlId"
                    target="_blank"
                    class="link-detail"
                    @click.stop
                  >
                    Detail
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
        <button @click="scrollTimeline(100)" class="nav-btn right">›</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';

const props = defineProps({
  searchData: {
    type: Object,
    required: true
  }
});

// State
const isExpanded = ref(false);
const isMobile = ref(false);
const timelineContainer = ref(null);
const timelineTrack = ref(null);

// Computed
const query = computed(() => props.searchData.query);
const files = computed(() => props.searchData.top_files || []);
const timeline = computed(() => props.searchData.timeline || []);

// Methods
const openLink = (url) => {
  window.open(url, '_blank');
};

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value;
};

const scrollTimeline = (amount) => {
  if (timelineContainer.value) {
    timelineContainer.value.scrollBy({
      left: amount,
      behavior: 'smooth'
    });
  }
};

const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('de-DE', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit' 
  });
};

const formatRange = (start, end) => {
  const startDate = new Date(start);
  const endDate = new Date(end);
  
  if (start === end) {
    return startDate.toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }
  
  return `${startDate.toLocaleDateString('de-DE', { 
    year: 'numeric', 
    month: 'short', 
    day: 'numeric' 
  })} – ${endDate.toLocaleDateString('de-DE', { 
    year: 'numeric', 
    month: 'short', 
    day: 'numeric' 
  })}`;
};

const formatType = (type) => {
  const map = {
    'Meeting': 'Sitzung',
    'Paper': 'Dokument',
    'AgendaItem': 'TOP',
    'Consultation': 'Beratung',
    'Organization': 'Organisation'
  };
  return map[type] || type;
};

const formatTime = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// Responsive check
const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768;
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
});

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile);
});
</script>

<style scoped>
/* Container */
.search-results-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: system-ui, -apple-system, sans-serif;
}

/* Header */
.query-header {
  margin-bottom: 24px;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.query-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  word-break: break-word;
}

/* Cards */
.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 24px;
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.card-title {
  margin: 0 0 16px 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  border-bottom: 2px solid #667eea;
  padding-bottom: 8px;
}

/* Files List */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-item-wrapper {
  transition: all 0.3s ease;
}

.is-hidden {
  display: none;
}

.file-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  text-decoration: none;
  transition: all 0.2s ease;
  cursor: pointer;
}

.file-link:hover {
  background: #f3f4f6;
  border-color: #667eea;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(102, 126, 234, 0.1);
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.file-name {
  font-weight: 500;
  color: #1f2937;
  font-size: 0.95rem;
}

.file-meta {
  font-size: 0.85rem;
  color: #6b7280;
}

.download-btn {
  background: #667eea;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease;
  white-space: nowrap;
  margin-left: 12px;
}

.download-btn:hover {
  background: #5a6fd6;
}

.toggle-btn {
  width: 100%;
  padding: 12px;
  background: transparent;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  color: #6b7280;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
  margin-top: 8px;
}

.toggle-btn:hover {
  border-color: #667eea;
  color: #667eea;
  background: #f9fafb;
}

/* Timeline Controls */
.timeline-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 50%;
  font-size: 1.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.nav-btn:hover {
  background: #5a6fd6;
  transform: scale(1.1);
}

.nav-btn:disabled {
  background: #d1d5db;
  cursor: not-allowed;
}

/* Timeline Scroll Wrapper */
.timeline-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding: 10px 0;
  /* Custom scrollbar styling */
  scrollbar-width: thin;
  scrollbar-color: #667eea #f3f4f6;
}

/* Webkit browsers scrollbar */
.timeline-wrapper::-webkit-scrollbar {
  height: 12px;
}

.timeline-wrapper::-webkit-scrollbar-track {
  background: #f3f4f6;
  border-radius: 6px;
}

.timeline-wrapper::-webkit-scrollbar-thumb {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 6px;
  border: 3px solid #f3f4f6;
}

.timeline-wrapper::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(135deg, #5a6fd6 0%, #6a4191 100%);
}

/* Timeline Track */
.timeline-scroll-track {
  display: flex;
  gap: 20px;
  padding: 8px 4px;
  min-width: fit-content;
}

/* Individual Timeline Card */
.timeline-card-item {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  min-width: 320px;
  flex-shrink: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.timeline-card-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.date-range {
  font-weight: 600;
  color: #667eea;
  margin-bottom: 12px;
  font-size: 0.9rem;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-chip {
  padding: 10px;
  background: white;
  border-left: 4px solid #667eea;
  border-radius: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  transition: all 0.2s ease;
}

.event-chip:hover {
  background: #f9fafb;
}

.tag {
  background: #dbeafe;
  color: #1e40af;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  flex-shrink: 0;
}

.title {
  flex: 1;
  font-size: 0.85rem;
  color: #374151;
  min-width: 120px;
  line-height: 1.4;
}

.sub-date {
  font-size: 0.75rem;
  color: #6b7280;
  white-space: nowrap;
}

.link-detail {
  font-size: 0.75rem;
  color: #667eea;
  text-decoration: none;
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.link-detail:hover {
  background: #eff6ff;
  text-decoration: underline;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .search-results-container {
    padding: 12px;
  }

  .card {
    padding: 16px;
  }

  .query-header h2 {
    font-size: 1rem;
  }

  .timeline-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .nav-btn {
    width: 100%;
    border-radius: 8px;
  }

  .timeline-wrapper {
    overflow-x: auto;
    height: auto;
  }

  .timeline-scroll-track {
    flex-direction: column;
    gap: 16px;
  }

  .timeline-card-item {
    min-width: 100%;
    width: 100%;
  }

  .file-link {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .download-btn {
    width: 100%;
    margin-left: 0;
  }
}
</style>
