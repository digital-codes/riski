<script setup lang="ts">
import { computed } from "vue";

interface RelatedDoc {
  oparl_key: string;
  shared: number;
  score: number;
  shared_tags: string[];
  name: string;
  downloadurl?: string;
}

const props = defineProps<{ docs: RelatedDoc[] }>();
const has = computed(() => (props.docs || []).length > 0);
function link(r: RelatedDoc) {
  return r.downloadurl || `https://web2.karlsruhe.de/ris/oparl/bodies/0001/files/${r.oparl_key?.split("/").pop()}`;
}
</script>

<template>
  <div v-if="has" class="related-docs">
    <h3>Thematisch verwandte Dokumente</h3>
    <ul>
      <li v-for="d in props.docs" :key="d.oparl_key">
        <a :href="link(d)" target="_blank" rel="noopener">{{ d.name }}</a>
        <span class="tags" :title="d.shared_tags.join(', ')">{{ d.shared_tags.join(", ") }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.related-docs h3 { font-size: 1rem; margin: 0 0 .4rem; }
.related-docs ul { list-style: none; margin: 0; padding: 0; }
.related-docs li { padding: .2rem 0; }
.related-docs .tags { color: #666; font-size: .82em; margin-left: .5rem; }
</style>
