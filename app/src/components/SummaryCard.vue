<template>
	<section class="summary-card">
		<header class="summary-header">
			<h2>Summary</h2>
			<button type="button" class="pdf-btn" @click="downloadPdf" title="Zusammenfassung drucken oder als PDF speichern">
				Als PDF speichern
			</button>
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

// Renders the markdown into a hidden iframe and triggers the browser's
// print dialog scoped to that frame — "Save as PDF" is a native target
// there. This keeps formatting (headings, bold, lists, umlauts) without a
// PDF library, and avoids popup blockers entirely.
const downloadPdf = () => {
	const css = `
		body { font-family: system-ui, -apple-system, sans-serif; color: #1f2937;
		       max-width: 720px; margin: 2.5rem auto; line-height: 1.6; }
		h1, h2, h3 { color: #111827; margin: 0.8em 0 0.4em; }
		code { background: #f1f5f9; padding: 0.1rem 0.35rem; border-radius: 4px; }
		pre { background: #0b1220; color: #e5e7eb; padding: 0.8rem; border-radius: 8px;
		      white-space: pre-wrap; }
		@media print { body { margin: 1cm auto; } }
	`;
	const iframe = document.createElement('iframe');
	Object.assign(iframe.style, {
		position: 'fixed', width: '0', height: '0', border: '0', visibility: 'hidden',
	});
	document.body.appendChild(iframe);

	const doc = iframe.contentDocument || iframe.contentWindow.document;
	doc.open();
	doc.write(
		`<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">` +
		`<title>RISKI Zusammenfassung</title><style>${css}</style></head><body>` +
		`<h1>RISKI Zusammenfassung</h1>${renderedSummary.value}</body></html>`
	);
	doc.close();

	let printed = false;
	const doPrint = () => {
		if (printed) return;
		printed = true;
		try {
			iframe.contentWindow.focus();
			iframe.contentWindow.print();
		} catch (e) { /* ignore — user can reload */ }
	};
	// remove the iframe once the dialog closes (print, save, or cancel)
	iframe.contentWindow.addEventListener('afterprint', () => setTimeout(() => iframe.remove(), 300));
	iframe.onload = doPrint;
	setTimeout(doPrint, 250); // fallback if onload already fired
};
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
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.pdf-btn {
	background: #667eea;
	color: white;
	border: none;
	padding: 8px 16px;
	border-radius: 6px;
	font-weight: 500;
	cursor: pointer;
	transition: background 0.2s ease;
	white-space: nowrap;
}

.pdf-btn:hover {
	background: #5a6fd6;
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
