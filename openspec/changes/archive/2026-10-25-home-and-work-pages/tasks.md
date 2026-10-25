# Tasks

## 1. Routing and shell skeleton

- [x] 1.1 Add a `useHashRoute()` composable (`app/src/router.js` or similar) reading/writing `location.hash` with routes `#/`, `#/work`, `#/datenschutz`, `#/impressum` and a default of `#/`; verify by importing it in a scratch check that hash changes produce route changes.
- [x] 1.2 Create `SiteNav.vue` (logo image from `app/src/assets` linking home, links to Work, Datenschutz, Impressum) and `SiteFooter.vue` (attribution + legal links); render both in `App.vue` around a route-switched content area; verify with `npm run dev` that navbar and footer appear on every route and the logo links home.

## 2. Move search UI into WorkPage

- [x] 2.1 Move the current `App.vue` template, script and styles verbatim into `components/WorkPage.vue` (including async NetworkView/GeoMap imports and all search state); trim `App.vue` to shell + routing only; verify `npm run build` succeeds and a search (or sample-data fallback) still renders results on `#/work`.
- [x] 2.2 Verify the work page scrolls as a normal document (no fixed-height ancestors, `overflow` not hidden) and the DetailPanel still renders correctly inside the scrolled page; adjust to `position: fixed`/minimal CSS if broken.

## 3. Home and legal pages

- [x] 3.1 Create `HomePage.vue`: hero with `riski-logo.png`, short riski description (Karlsruhe Ratsinformationssystem, semantic search/timeline), a GDPR/privacy note section, imprint link, and a prominent call-to-action linking to `#/work`; verify rendering and that the CTA navigates to the work page.
- [x] 3.2 Create `LegalPage.vue` (or two small components) rendering placeholder Datenschutz content (honest note: prototype, no tracking cookies, data from public OParl) and dummy Impressum content (placeholder name/address); verify both are reachable from navbar and footer links.
- [x] 3.3 Make home, legal, navbar and footer responsive (single column, readable text at ~360–768px viewport via media queries); verify by resizing the devTools viewport with no horizontal scrolling on these pages.

## 4. Integration check

- [x] 4.1 Full pass over all routes in dev and `npm run build` + `npm run preview`: search works on `#/work`, deep-link via hash opens the right page, mobile layout best-effort accepted; confirm no console errors from the shell (echarts/leaflet lazy imports still load).
