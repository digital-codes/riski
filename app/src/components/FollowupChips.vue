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
  <!-- change: fix-gremium-session-docs-thread — chips are ALWAYS inside a
       card (user rule, 2026-11-25): follow-up questions got their own
       styled card instead of the bare chip row. -->
  <section v-if="props.questions && props.questions.length" class="followup-card">
    <header class="followup-card-head">
      <h3 class="followup-card-title">Mögliche Vertiefungen</h3>
      <p class="followup-card-sub">Anschlussfragen zum Thema — klicken, um sie zu stellen.</p>
    </header>
    <div class="followup-chips">
      <button
        v-for="(q, i) in props.questions"
        :key="i"
        @click="pick(q)"
        class="chip"
      >{{ q }}</button>
    </div>
  </section>
</template>

<style scoped>
.followup-card { max-width: 1200px; margin: 0 auto 24px; background: white; border: 1px solid #e5e7eb;
  border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); padding: 16px 20px; }
.followup-card-head h3 { margin: 0; font-size: 1rem; font-weight: 600; color: #1f2937;
  border-bottom: 2px solid #667eea; padding-bottom: 6px; }
.followup-card-sub { margin: .4rem 0 0; font-size: .82rem; color: #64748b; }
.followup-chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: .6rem 0 0; }
.chip { cursor: pointer; padding: .25rem .7rem; border-radius: 1rem; border: 1px solid #ccc; background: #f7f7f7; }
.chip:hover { background: #eee; }
</style>
