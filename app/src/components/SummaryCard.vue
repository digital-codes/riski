<template>
	<section class="summary-card">
		<header class="summary-header">
			<h2>Summary</h2>
		</header>

		<div class="summary-body" v-html="renderedSummary"></div>
	</section>
</template>

<script setup>
import { computed } from 'vue';
import MarkdownIt from 'markdown-it';

const props = defineProps({
	summary: {
		type: [String, Array, Object],
		default: ''
	}
});

const md = new MarkdownIt({
	breaks: true,
	linkify: true,
	typographer: true
});

const summaryText = computed(() => {
	if (Array.isArray(props.summary)) {
		return props.summary.join('\n');
	}
	if (props.summary && typeof props.summary === 'object') {
		return JSON.stringify(props.summary, null, 2);
	}
	return props.summary || '';
});

const renderedSummary = computed(() => md.render(summaryText.value));
</script>

<style scoped>
.summary-card {
	margin: 0 auto 24px;
	max-width: 1200px;
	background: white;
	border-radius: 12px;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	padding: 24px;
	margin-bottom: 24px;
	border: 1px solid #e5e7eb;
}

.summary-header {
	margin: 0 0 16px 0;
}

.summary-header h2 {
	margin: 0;
	font-size: 1.125rem;
	font-weight: 600;
	color: #1f2937;
	border-bottom: 2px solid #667eea;
	padding-bottom: 8px;
}

.summary-body {
	padding: 0;
	color: #334155;
	line-height: 1.65;
}

.summary-body :deep(h1),
.summary-body :deep(h2),
.summary-body :deep(h3) {
	color: #111827;
	margin: 0.6em 0 0.35em;
}

.summary-body :deep(p) {
	margin: 0.55em 0;
}

.summary-body :deep(ul),
.summary-body :deep(ol) {
	padding-left: 1.2rem;
	margin: 0.45em 0;
}

.summary-body :deep(code) {
	background: #f1f5f9;
	padding: 0.1rem 0.35rem;
	border-radius: 4px;
	font-size: 0.9em;
}

.summary-body :deep(pre) {
	background: #0b1220;
	color: #e5e7eb;
	border-radius: 8px;
	padding: 0.8rem;
	overflow-x: auto;
}

@media (max-width: 768px) {
	.summary-card {
		padding: 16px;
	}
}
</style>
