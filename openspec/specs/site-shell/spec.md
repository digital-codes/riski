## Purpose

Defines the navigation shell of the riski web app: a shared navbar and footer, page navigation between a home page, a work page hosting the existing search UI, and placeholder legal pages (Datenschutz, Impressum).

## Requirements

### Requirement: Site shell with navbar and footer
The web app SHALL render a top navbar on every page containing the riski logo (one of the images from `app/src/assets`) linked to the home page, a link to the work page, and links to the legal pages. The app SHALL render a footer on every page containing short project attribution and links to the legal pages.

#### Scenario: Navbar on all pages
- **WHEN** the user navigates to any page of the app
- **THEN** the navbar with logo and page links is visible at the top

#### Scenario: Footer on all pages
- **WHEN** the user navigates to any page of the app
- **THEN** a footer with legal links is visible at the bottom of the page content

#### Scenario: Logo links home
- **WHEN** the user clicks the logo in the navbar
- **THEN** the app navigates to the home page

### Requirement: Home page content
The app SHALL serve a home page at the root route containing: a hero section with the riski logo image, a short description of what riski does (explanation of the Karlsruhe Ratsinformationssystem), a GDPR/privacy note section, and a link to the imprint page. The home page SHALL offer a prominent entry point into the work page.

#### Scenario: Home page renders
- **WHEN** the user opens the app root URL
- **THEN** the home page is shown with logo, project description, privacy note, and imprint link

#### Scenario: Entry to work page
- **WHEN** the user clicks the primary call-to-action on the home page
- **THEN** the app navigates to the work page

### Requirement: Work page hosts the search UI and scrolls
The app SHALL render the existing search/exploration UI (search bar, network view, summary, topic list, geo map, timeline, detail panel) inside a work page container that has the shared navbar and footer. Unlike a fixed-viewport app frame, the work page SHALL scroll as a normal document page.

#### Scenario: Search UI available on work page
- **WHEN** the user navigates to the work page
- **THEN** the existing search UI is rendered and a search can be started as before

#### Scenario: Page scrolls
- **WHEN** the search produces results extending beyond the viewport
- **THEN** the user can scroll the page normally to reach all sections (network view, summary, map, timeline)

### Requirement: Placeholder legal pages
The app SHALL provide a Datenschutz (GDPR) page and an Impressum page reachable from navbar and footer, containing prototype-grade placeholder content (dummy imprint data; a short honest privacy note stating what the prototype stores, e.g. no tracking cookies).

#### Scenario: Legal pages reachable
- **WHEN** the user clicks "Datenschutz" or "Impressum" in the navbar or footer
- **THEN** the corresponding placeholder page is displayed

### Requirement: Prototype-grade mobile layout
The home page, legal pages, navbar and footer SHALL remain readable and usable on small screens (best effort). The work page SHALL degrade gracefully on small screens; degraded rendering of the network view on small screens is accepted for this prototype.

#### Scenario: Home page on a phone
- **WHEN** the home page is viewed at a mobile viewport width
- **THEN** text is readable without horizontal scrolling and navigation remains reachable
