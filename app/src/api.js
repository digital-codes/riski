// RISKI API client (change: api-search-expand, task 2.1)
// The API is addressed same-origin under /api/... — in production the web
// server maps $HOMEURL/api/... to the FastAPI service; in dev the vite
// proxy (vite.config.js) forwards /api/... to localhost:8000. Override
// with VITE_API_BASE for a direct API host if ever needed.
const API_BASE = import.meta.env?.VITE_API_BASE || '/api';

async function post(path, body) {
	const res = await fetch(`${API_BASE}${path}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const err = await res.json();
			if (err.detail) detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
		} catch { /* non-json error body */ }
		throw new Error(`${path} failed: ${detail}`);
	}
	return res.json();
}

export async function search(query, { topK = 10, filters, signals, summarize = false } = {}) {
	return post('/search', { query, top_k: topK, filters, signals, summarize });
}

// change: intent-router — routed question answering; same result contract
// as /search plus intent/slots/applied_filters/fallback_notes
export async function ask(query, { sessionId, topK = 10, signals, summarize = false } = {}) {
	return post('/ask', { query, session_id: sessionId, top_k: topK, signals, summarize });
}

export async function summarize(sessionId, { refine = false, exclude = [] } = {}) {
	// change: summary-refine-file-control — refine re-runs the summarizer
	// with full content; exclude changes the session's document set
	return post('/summarize', { session_id: sessionId, refine, exclude });
}

export async function expand(nodeId, limitPerRelation = 25) {
	return post('/expand', { node_id: nodeId, limit_per_relation: limitPerRelation });
}

export async function facets() {
	const res = await fetch(`${API_BASE}/facets`);
	if (!res.ok) throw new Error(`/facets failed: ${res.statusText}`);
	return res.json();
}

export function geoUrl(sessionId) {
	return `${API_BASE}/geo/${sessionId}`;
}
