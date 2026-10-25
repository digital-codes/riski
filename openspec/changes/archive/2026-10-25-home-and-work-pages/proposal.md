# Proposal

## Why

The web app currently dumps the user straight into the search view with no context: there is no landing page explaining what riski is, no navigation, no legal pages (GDPR note / imprint). As a public-facing prototype, it needs a presentable shell — a home page with a short description and the riski logo, plus a "work" page that hosts the existing search/exploration UI inside a common navbar-and-footer layout, similar in feel to the auenlaend chatbot site.

## What Changes

- Add a site shell to the Vue app: a top navbar with the riski logo and links, and a footer with links to legal pages.
- Add a **home page** (`/`): short project description, a hero with one of the logo images from `app/src/assets`, links to the work page, a GDPR/privacy note section, and a link to a dummy imprint.
- Add a **work page** (`/work`): a container page with navbar and footer that embeds the existing search UI (search bar, network view, summary, topics, map, timeline) as a scrollable section — unlike the fixed-viewport auenlaend layout, the page scrolls normally.
- Add lightweight client-side routing (no router dependency required; hash-based or a tiny view switch is acceptable for a prototype).
- Add placeholder legal pages: **Datenschutz (GDPR)** note and **Impressum** (dummy content, clearly prototype-grade).
- Mobile: best-effort responsive layout. The network view has known limitations on small screens — that is accepted for this prototype; pages themselves should remain usable.
- Keep all existing app behaviour (search, expand, summarize, refine, geo map) working unchanged inside the work page container.

## Capabilities

### New Capabilities
- `site-shell`: navigation shell of the web app — navbar with logo, footer, page routing between home, work, and legal pages; home page content (description, logo, GDPR note, imprint link); scrollable work page hosting the search UI.

### Modified Capabilities
<!-- none — the search UI behaviour itself is unchanged, it only moves into a container -->

## Impact

- `app/src/App.vue` — becomes the shell (navbar/footer/router) instead of directly rendering the search UI.
- New files: `app/src/components/HomePage.vue`, `WorkPage.vue`, `LegalPage.vue` (or similar), moving the current App.vue content into the work page component.
- `app/index.html` — title/lang may be updated.
- No backend, API, or pipeline changes. No new dependencies required for a prototype (hash routing in plain Vue).
