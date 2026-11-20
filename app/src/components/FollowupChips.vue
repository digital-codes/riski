<script setup lang="ts">
const props = defineProps<{
  questions: string[];
  state: string;
  sessionId: string;
}>();
const emit = defineEmits<{ (e: "pick", question: string, state: string, sessionId: string): void }>();
function pick(q: string) {
  emit("pick", q, props.state, props.sessionId);
}
</script>

<template>
  <div v-if="props.questions && props.questions.length" class="followup-chips">
    <button
      v-for="(q, i) in props.questions"
      :key="i"
      @click="pick(q)"
      class="chip"
    >{{ q }}</button>
  </div>
</template>

<style scoped>
.followup-chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: .5rem 0; }
.chip { cursor: pointer; padding: .25rem .7rem; border-radius: 1rem; border: 1px solid #ccc; background: #f7f7f7; }
.chip:hover { background: #eee; }
</style>
