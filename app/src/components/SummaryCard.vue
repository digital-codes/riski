<template>
	<section class="summary-card">
		<header class="summary-header">
			<h2>
				Zusammenfassung. <span class="disclaimer">{{ instance.aiDisclaimer }}</span>
				<span v-if="loading" class="loading-note">
					<span class="header-spinner"></span> Zusammenfassung wird erstellt…
				</span>
				<span v-else-if="refining" class="loading-note">
					<span class="header-spinner"></span> Verfeinere Zusammenfassung (Volltext)…
				</span>
				<span v-else-if="mapAvailable" class="loading-note map-note" title="Zu den Suchergebnissen gehört eine Karte — weiter unten auf der Seite">
					📍 Karte verfügbar — weiter unten
				</span>
			</h2>
			<div class="header-actions">
				<button v-if="!loading && summary" type="button" class="refine-btn"
						:disabled="refining || refined"
						@click="$emit('refine')"
						:title="refined
							? 'Volltext-Zusammenfassung aktiv — Dokumente ein-/ausschließen für Änderungen'
							: 'Zusammenfassung mit dem Volltext der Dokumente neu erstellen (dauert etwas länger)'">
					{{ refining ? 'Verfeinere…' : 'Verfeinern' }}
				</button>
				<button v-if="!loading && summary" type="button" class="pdf-btn" @click="downloadPdf" title="Zusammenfassung drucken oder als PDF speichern">
					Als PDF speichern
				</button>
			</div>
		</header>

		<div v-if="!loading" class="summary-body" v-html="renderedSummary"></div>

		<!-- kg-app-integration: "Auswahl" — clustered follow-up chips in the
		     header block (clarification mode), and the related docs card
		     below with name/year/teaser detail -->
		<div v-if="kgChips && kgChips.length" class="kg-selection">
			<h3 class="kg-selection-title">Auswahl</h3>
			<div class="kg-chips">
				<button v-for="(chip, i) in kgChips" :key="i" type="button"
						class="kg-chip" @click="$emit('pick', chip)">
					<span class="kg-chip-topic">{{ chip.topic }}</span>
					<span v-if="chip.example" class="kg-chip-example">{{ chip.example }}</span>
				</button>
			</div>
		</div>
		<div v-if="kgRelated && kgRelated.length" class="kg-related">
			<h3 class="kg-related-title">Thematisch verwandte Dokumente (nach den gewählten Themen)</h3>
			<ul class="kg-related-list">
				<li v-for="doc in kgRelated" :key="doc.oparl_key">
					<a v-if="doc.downloadurl" :href="doc.downloadurl" target="_blank" rel="noopener" class="kg-related-link">
						<span class="kg-related-name">{{ doc.name }}</span>
						<span v-if="doc.year" class="kg-related-year">{{ doc.year }}</span>
					</a>
					<span v-else class="kg-related-name">{{ doc.name }}</span>
					<div v-if="doc.teaser" class="kg-related-teaser">{{ doc.teaser }}</div>
					<span class="kg-related-tags">{{ doc.shared_tags.join(', ') }}</span>
				</li>
			</ul>
		</div>

		<div v-if="!loading && files.length" class="file-list">
			<ul class="file-items">
				<li v-for="f in files" :key="f.oparlKey" :class="{ excluded: f.excluded }">
					<div v-if="f.via" class="via-label">{{ f.via }}</div>
					<label class="file-item">
						<input type="checkbox" :checked="!f.excluded"
							   :disabled="refining"
							   @change="$emit('toggle-file', { oparlKey: f.oparlKey, excluded: !$event.target.checked })" />
						<span v-if="f.index" class="file-num">Datei {{ f.index }}</span>
						<a v-if="f.downloadUrl" :href="f.downloadUrl" target="_blank" rel="noopener" class="file-name">{{ f.name }}</a>
						<span v-else class="file-name">{{ f.name }}</span>
					</label>
				</li>
			</ul>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from 'vue';
import MarkdownIt from 'markdown-it';
import { instance } from '../instanceStore.js';

const props = defineProps({
	summary: {
		type: [String, Array, Object],
		default: ''
	},
	loading: {
		type: Boolean,
		default: false
	},
	mapAvailable: {
		type: Boolean,
		default: false
	},
	// kg-app-integration: cluster chips (Auswahl) + related docs card
	kgChips: {
		type: Array,
		default: () => []
	},
	kgRelated: {
		type: Array,
		default: () => []
	},
	// structured per-file metadata from /summarize (change: summary-refine-file-control)
	files: {
		type: Array,
		default: () => []
	},
	refining: {
		type: Boolean,
		default: false
	},
	// full-content mode reached — refine button disabled (toggles still re-run)
	refined: {
		type: Boolean,
		default: false
	}
});

const emit = defineEmits(['pick', 'refine', 'toggle-file']);



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
			li.doc-excluded { color: #9ca3af; }
		li.doc-excluded a { color: #9ca3af; }
		@media print { body { margin: 1cm auto; } }
	`;
	const iframe = document.createElement('iframe');
	Object.assign(iframe.style, {
		position: 'fixed', width: '0', height: '0', border: '0', visibility: 'hidden',
	});
	document.body.appendChild(iframe);

	const doc = iframe.contentDocument || iframe.contentWindow.document;
	// full document list with status (all files, not just the considered
	// ones — the printout should document the complete selection state)
	const fileListHtml = props.files.length
		? `<h2>Dokumente</h2><ul>` +
		  props.files.map(f => {
				const name = f.downloadUrl
					? `<a href="${f.downloadUrl}">${f.name ?? f.oparlKey}</a>`
					: (f.name ?? f.oparlKey);
				const status = f.excluded
					? ` <em>(nicht berücksichtigt)</em>`
					: '';
				return `<li class="${f.excluded ? 'doc-excluded' : ''}">${name}${status}</li>`;
			}).join('') + `</ul>`
		: '';
	doc.open();
	doc.write(
		`<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">` +
		`<title>RISKI Zusammenfassung</title><style>${css}	.kg-selection { margin: .4rem 0; }
	.kg-selection-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: .2rem 0 .4rem; }
	.kg-chips { display: flex; flex-wrap: wrap; gap: .5rem; }
	.kg-chip { cursor: pointer; border: 1px solid #cbd5e1; border-radius: .7rem; background: #f1f5f9;
	           padding: .45rem .8rem; text-align: left; }
	.kg-chip:hover { background: #e2e8f0; }
	.kg-chip-topic { display: block; font-weight: 600; color: #1e293b; }
	.kg-chip-example { display: block; font-size: .78em; color: #667; margin-top: .15rem; }
	.kg-related { margin: 1rem 0 0; border-top: 1px solid #e2e8f0; padding-top: .6rem; }
	.kg-related-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: 0 0 .5rem; }
	.kg-related-list { list-style: none; margin: 0; padding: 0; }
	.kg-related-list li { margin: .35rem 0; padding: .4rem .6rem; border: 1px solid #eee; border-radius: .4rem; background: #f8fafc; }
	.kg-related-link { text-decoration: none; color: #1d4ed8; }
	.kg-related-name { font-weight: 600; }
	.kg-related-year { color: #888; margin-left: .4rem; }
	.kg-related-teaser { color: #444; font-size: .84em; margin-top: .25rem; }
	.kg-related-tags { color: #90a; display: inline-block; font-size: .75em; margin-top: .25rem; }
</style></head><body>` +
		`<h1>RISKI Zusammenfassung</h1>${renderedSummary.value}${fileListHtml}</body></html>`
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

.header-actions {
	display: flex;
	gap: 8px;
	align-items: center;
}

.refine-btn {
	background: white;
	color: #667eea;
	border: 1px solid #667eea;
	padding: 8px 16px;
	border-radius: 6px;
	font-weight: 500;
	cursor: pointer;
	transition: background 0.2s ease, color 0.2s ease;
	white-space: nowrap;
}

.refine-btn:hover {
	background: #667eea;
	color: white;
}

.refine-btn:disabled {
	opacity: 0.6;
	cursor: wait;
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
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	flex: 1;
}

.disclaimer {
	font-weight: 600;
	color: red;
	margin-left: 8px;
	margin-right:auto;

}

.loading-note {
	display: inline-flex;
	align-items: center;
	gap: 8px;
	font-size: 0.85rem;
	font-weight: 400;
	color: #6b7280;
}

.map-note {
	color: #667eea;
}

.header-spinner {
	width: 14px;
	height: 14px;
	border: 2.5px solid #e5e7eb;
	border-top-color: #667eea;
	border-radius: 50%;
	animation: spin 0.8s linear infinite;
	display: inline-block;
}

@keyframes spin {
	to { transform: rotate(360deg); }
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

/* interactive file list (change: summary-refine-file-control) */
.file-list {
	margin-top: 16px;
	border-top: 1px solid #e5e7eb;
	padding-top: 10px;
}

.file-list-toggle {
	background: none;
	border: none;
	color: #6b7280;
	font-size: 0.85rem;
	cursor: pointer;
	padding: 4px 0;
}

.via-label {
	margin: 8px 0 2px;
	font-size: 0.75rem;
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: #764ba2;
}

.file-items {
	list-style: none;
	margin: 6px 0 0;
	padding: 0;
}

.file-item {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 4px 0;
	font-size: 0.9rem;
	cursor: pointer;
}

.file-item input {
	cursor: pointer;
}

.file-item.excluded .file-name {
	text-decoration: line-through;
	color: #9ca3af;
}

.file-num {
	color: #6b7280;
	font-size: 0.8rem;
	min-width: 52px;
}

.file-name {
	color: #667eea;
	text-decoration: none;
}

a.file-name:hover {
	text-decoration: underline;
}


@media (max-width: 768px) {
	.summary-card {
		padding: 16px;
	}
}
	.kg-selection { margin: .4rem 0; }
	.kg-selection-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: .2rem 0 .4rem; }
	.kg-chips { display: flex; flex-wrap: wrap; gap: .5rem; }
	.kg-chip { cursor: pointer; border: 1px solid #cbd5e1; border-radius: .7rem; background: #f1f5f9;
	           padding: .45rem .8rem; text-align: left; }
	.kg-chip:hover { background: #e2e8f0; }
	.kg-chip-topic { display: block; font-weight: 600; color: #1e293b; }
	.kg-chip-example { display: block; font-size: .78em; color: #667; margin-top: .15rem; }
	.kg-related { margin: 1rem 0 0; border-top: 1px solid #e2e8f0; padding-top: .6rem; }
	.kg-related-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: 0 0 .5rem; }
	.kg-related-list { list-style: none; margin: 0; padding: 0; }
	.kg-related-list li { margin: .35rem 0; padding: .4rem .6rem; border: 1px solid #eee; border-radius: .4rem; background: #f8fafc; }
	.kg-related-link { text-decoration: none; color: #1d4ed8; }
	.kg-related-name { font-weight: 600; }
	.kg-related-year { color: #888; margin-left: .4rem; }
	.kg-related-teaser { color: #444; font-size: .84em; margin-top: .25rem; }
	.kg-related-tags { color: #90a; display: inline-block; font-size: .75em; margin-top: .25rem; }
</style>
