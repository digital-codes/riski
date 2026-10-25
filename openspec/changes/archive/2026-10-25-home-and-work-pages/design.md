# Design

## Context

`app/src/App.vue` currently renders the whole search UI directly (search bar, RouteInfo, NetworkView, DetailPanel, TopicList/SummaryCard, GeoMap, TimeLine) with no shell around it. The app is a plain Vue 3 + Vite setup with no router, no UI framework, and hand-written CSS. Logo assets exist in `app/src/assets` (`riski-logo.png`, `riski.png`, `riski_nokg.png`, small variants). The visual reference is the auenlaend chatbot app (navbar with centered logo, info/chat pages, sidebar), but auenlaend uses a fixed-height layout with per-pane scrolling — riski should instead use a normal scrolling document, and a prototype should not take on auenlaend's dependency stack (vuestic-ui, vue-i18n).

## Goals / Non-Goals

**Goals:**
- Reusable shell: one `AppShell`-style layout providing navbar + footer + routed content slot.
- Move the current search UI wholesale into a `WorkPage` component; no behavioural changes to search logic.
- Home, Datenschutz, Impressum as simple content components.
- Reasonable mobile behaviour for shell and content pages; accepted degradation of network view on phones.

**Non-Goals:**
- No UI framework, i18n, theming/dark-mode, or real server-rendered pages.
- No real legal content — imprint/privacy text is placeholder.
- No redesign of the existing search components themselves.
- No backend changes.

## Decisions

- **Routing: hand-rolled hash router, no vue-router.** A tiny `useHashRoute()` composable reading/writing `location.hash` (`#/`, `#/work`, `#/datenschutz`, `#/impressum`) is ~30 lines and keeps the dependency list untouched. Alternative considered: `vue-router` — overkill for 4 static pages in a prototype; can be swapped in later without component changes since pages are self-contained.
- **App.vue becomes the shell.** Current App.vue template+search state moves unchanged into `components/WorkPage.vue`. App.vue keeps only router state, `SiteNav.vue`, `SiteFooter.vue`, and dynamic `<component :is>`/`v-if` switching. Risk: large file move — mitigate by moving template and script verbatim first, then trimming App.vue, then a smoke test (`npm run build`).
- **Logo choice: `riski-logo.png` on the home hero, small variant in the navbar.** Alternatives (`riski.png`, `riski_nokg.png`) stay available; pick during implementation by visual check.
- **Scrolling:** page scrolls as a normal document (`min-height: 100vh` flex column, footer after content). The work page container is a plain `max-width` wrapper like today's `.wrapper`; no `overflow: hidden` on ancestors. Existing DetailPanel uses fixed/modoverlay-style positioning — verify it still renders correctly inside a scrolled page and adjust to `position: fixed` if needed.
- **Styling:** extend the existing hand-written CSS idiom (system-ui, `#667eea` accent gradient, rounded cards). No CSS framework.
- **Mobile:** shell uses a simple approach — navbar collapses to logo + a compact menu (or stacked links) below ~768px; content pages are single-column via media queries. NetworkView keeps its current mobile behaviour (it already receives `isMobile`); no new effort beyond container correctness.

## Risks / Trade-offs

- [Moving App.vue content can silently break search state wiring] → move code verbatim into WorkPage.vue, run `npm run build` and a manual smoke test against sample data fallback.
- [DetailPanel/overlay components assume the old layout] → check absolute/fixed positioning inside the new container; fix with minimal CSS only.
- [Hash routing not SEO-friendly / no deep-link paths] → accepted for a prototype; URLs still shareable via hash.
- [Network view unusable on small screens] → accepted per user ("best effort"); work page still scrolls so other panes (summary, topics, timeline) are reachable.

## Migration Plan

Single frontend change, no data migration. Deploy is a rebuild of `app/dist`. Rollback = `git revert`.

## Open Questions

None.
