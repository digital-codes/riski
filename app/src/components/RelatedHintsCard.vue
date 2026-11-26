<template>
	<section class="related-hints-card">
		<header class="hints-header">
			<h2 class="hints-title">Verfeinerung &amp; verwandte Dokumente</h2>
			<p class="hints-sub">
				Wählen Sie ein Thema, um die Suche zu präzisieren — oder vertiefen Sie eines der thematisch verwandten Dokumente.
			</p>
		</header>
		<p v-if="hint" class="hints-note">{{ hint }}</p>
		<div v-if="chips && chips.length" class="kg-selection">
			<h3 class="kg-selection-title">Auswahl</h3>
			<div class="kg-chips">
				<button v-for="(chip, i) in chips" :key="i" type="button"
						class="kg-chip" @click="$emit('pick', chip)">
					<span class="kg-chip-topic">{{ chip.topic }}</span>
					<span v-if="chip.example" class="kg-chip-example">{{ chip.example }}</span>
				</button>
			</div>
		</div>
		<div v-if="related && related.length" class="kg-related">
			<h3 class="kg-related-title">Thematisch verwandte Dokumente (nach den gewählten Themen)</h3>
			<ul class="kg-related-list">
				<li v-for="doc in related" :key="doc.oparl_key">
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
	</section>
</template>

<script setup>
// change: rework-search-result-cards — the related section (refinement
// chips + related documents) leaves SummaryCard and becomes its own card.
// Rendered only when the result had NO topic focus above the threshold
// (topical summary off) — WorkPage decides visibility.
defineProps({
	// kg-app-integration: cluster chips (Auswahl). Both chip flows unify
	// here (change: fix-gremium-session-docs-thread): clarification chips
	// AND the weak-recall D7 chips — the latter with the server hint text.
	chips: {
		type: Array,
		default: () => []
	},
	// optional server hint for the chips (D7 weak recall)
	hint: {
		type: String,
		default: null
	},
	// kg-app-integration: related documents (name/year/teaser/tags)
	related: {
		type: Array,
		default: () => []
	}
});

defineEmits(['pick']);
</script>

<style scoped>
.related-hints-card {
	margin: 0 auto 24px;
	max-width: 1200px;
	background: white;
	border-radius: 12px;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	padding: 20px 24px;
	border: 1px solid #e5e7eb;
}

.hints-header h2 {
	margin: 0;
	font-size: 1.05rem;
	font-weight: 600;
	color: #1f2937;
	border-bottom: 2px solid #64748b;
	padding-bottom: 8px;
}

.hints-sub {
	margin: .5rem 0 0;
	font-size: .85rem;
	color: #64748b;
}

.hints-note {
	margin: .6rem 0 0;
	font-size: .85rem;
	color: #667eea;
}

.kg-chips { display: flex; flex-wrap: wrap; gap: .5rem; }
.kg-chip { cursor: pointer; border: 1px solid #cbd5e1; border-radius: .7rem; background: #f1f5f9;
           padding: .45rem .8rem; text-align: left; }
.kg-chip:hover { background: #e2e8f0; }
.kg-chip-topic { display: block; font-weight: 600; color: #1e293b; }
.kg-chip-example { display: block; font-size: .78em; color: #667; margin-top: .15rem; }
.kg-selection-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: .4rem 0 .4rem; }
.kg-related { margin: 1rem 0 0; }
.kg-related-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #888; margin: 0 0 .5rem; }
.kg-related-list { list-style: none; margin: 0; padding: 0; }
.kg-related-list li { margin: .35rem 0; padding: .4rem .6rem; border: 1px solid #eee; border-radius: .4rem; background: #f8fafc; }
.kg-related-link { text-decoration: none; color: #1d4ed8; }
.kg-related-name { font-weight: 600; }
.kg-related-year { color: #888; margin-left: .4rem; }
.kg-related-teaser { color: #444; font-size: .84em; margin-top: .25rem; }
.kg-related-tags { color: #90a; display: inline-block; font-size: .75em; margin-top: .25rem; }

@media (max-width: 768px) {
	.related-hints-card { padding: 14px; }
}
</style>
