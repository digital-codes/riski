// Instance configuration store (change: instance-agnostic-config).
//
// Fetches GET /instance once at startup and exposes the deployment's
// branding/map/legal settings reactively. Every field falls back to the
// current Karlsruhe defaults, so the app renders identically when the API
// is unreachable (sample-data mode, dev without backend).

import { reactive } from 'vue';
import { getInstance } from './api.js';

const DEFAULTS = {
	title: 'RISKI Karlsruhe',
	heading: 'Das Karlsruher Ratsinformationssystem — erklärt.',
	footer: 'riski — das Karlsruher Ratsinformationssystem erklären. Prototyp; Datenbasis: offene OParl-Daten der Stadt Karlsruhe.',
	defaultQuery: 'wo liegt die Governance für Digitalisierung bei der Stadt Karlsruhe',
	oparlLink: 'https://web1.karlsruhe.de/ris/oparl',
	imprintUrl: '/#/impressum',
	privacyUrl: '/#/datenschutz',
	city: 'Karlsruhe',
	mapCenter: [49.0069, 8.4037],
	mapZoom: 12,
	dataSources: [
		{ name: 'Sitzungskalender der Stadt Karlsruhe', url: 'https://sitzungskalender.karlsruhe.de/db/ratsinformation/start' },
	],
};

export const instance = reactive({ ...DEFAULTS, loaded: false });

let initPromise = null;

export function initInstance() {
	if (initPromise) return initPromise;
	initPromise = (async () => {
		try {
			const cfg = await getInstance();
			if (cfg) {
				const f = cfg.frontend || {};
				const g = cfg.geo || {};
				if (f.title) instance.title = f.title;
				if (f.heading) instance.heading = f.heading;
				if (f.footer) instance.footer = f.footer;
				if (f.default_query) instance.defaultQuery = f.default_query;
				if (f.oparl_link) instance.oparlLink = f.oparl_link;
				if (f.imprint_url) instance.imprintUrl = f.imprint_url;
				if (f.privacy_url) instance.privacyUrl = f.privacy_url;
				if (Array.isArray(f.data_sources) && f.data_sources.length) {
					instance.dataSources = f.data_sources;
				}
				if (g.city) instance.city = g.city;
				if (Array.isArray(g.map_center) && g.map_center.length === 2) {
					instance.mapCenter = g.map_center;
				}
				if (typeof g.map_zoom === 'number') instance.mapZoom = g.map_zoom;
			}
		} catch {
			/* unreachable API: keep the defaults */
		} finally {
			instance.loaded = true;
			document.title = instance.title;
		}
	})();
	return initPromise;
}
