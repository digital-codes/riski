<script setup>
// change: site-menu — Dokumentationsseite: was riski ist, welche
// RAG-Operationen implementiert sind und wie Nutzer:innen damit arbeiten.
const sections = [
  {
    id: 'was-ist-riski',
    title: 'Was ist riski?',
    paragraphs: [
      'riski macht den Inhalt des Karlsruher Ratsinformationssystems (RIS) — der Open-Data-Plattform der Stadt Karlsruhe — durchsuchbar und erklärbar. Das RIS enthält Sitzungen, Tagesordnungspunkte, Beschlussvorlagen („Papers“), Anträge, Anfragen und dazugehörige PDF-Dokumente im OParl-Format.',
      'Aus diesen Daten baut riski eine durchsuchbare Wissensbasis und beantwortet Fragen in natürlicher Sprache: „Was wurde zum Rückbau der Herrenalber Straße beschlossen?“ — mit Belegen, Zeitachse, Netzwerk und Karte.',
    ],
    bullets: [],
  },
  {
    id: 'oparl',
    title: 'OParl-Struktur — Reverse-Engineering der Daten',
    paragraphs: [
      'Der OParl-Endpunkt des RIS stellt die Daten als verknüpfte Objekte bereit (System, Body, Organization, Person, Meeting, AgendaItem, Paper, File, Consultation, Location, Membership, LegislativeTerm).',
      'riski crawlt diesen Endpunkt inkrementell (nur Änderungen seit dem letzten Lauf), validiert die Antwortseiten gegen den bisherigen Stand und importiert alles in ein relationales PostgreSQL-Schema. Die verstreuten Fremdschlüssel- und Verweisstrukturen des OParl-Formats werden dabei automatisch rekonstruiert („Reverse-Engineering“): welche Vorlage gehört zu welchem Tagesordnungspunkt, welche Sitzung berät ihn, welche PDFs hängen daran. Genau diese Verknüpfungen bilden später das Netzwerk und die Zeitachse.',
    ],
    bullets: [],
  },
  {
    id: 'suche',
    title: 'Vektor- und Fuzzy-Suche (hybrid recall)',
    paragraphs: [
      'Die Suche kombiniert mehrere Signale und führt sie mit einem RRF-Fusionsverfahren zusammen:',
    ],
    bullets: [
      'Lexikalische Suche — fehlertolerante („fuzzy“) Textsuche über Namen und Titel, damit auch Schreibvarianten und Tippfehler gefunden werden.',
      'Namens-Vektoren — semantische Einbettungen der Dokument- und Objektnamen; finden passende Dokumente auch ohne exakte Wortübereinstimmung.',
      'Inhalts-Vektoren — Einbettungen des Dokumentinhalts (aus OCR/Extraktion), für inhaltliche Ähnlichkeit über die volle Textlänge.',
      'Neu-Ranking — die Treffer aller Signale werden neu bewertet und zur Antwortmenge („top files“) zusammengeführt. Schwache Kandidaten fließen bewusst nicht in Karte und Netzwerk ein, um die Ergebnisse fokussiert zu halten.',
    ],
  },
  {
    id: 'zusammenfassungen',
    title: 'Dokumenten-Chunks, Zusammenfassungen und Teaser',
    paragraphs: [
      'Vollständige PDFs sind für die Suche zu unhandlich. Deshalb erzeugt riski verdichtete und zerlegte Ebenen:',
    ],
    bullets: [
      'Chunks — große Dokumente (über ~8.000 Zeichen) werden in sinnvolle Abschnitte (an Überschriften orientiert) zerlegt und jeder Abschnitt separat eingebettet: die Suche findet damit auch Inhalte tief im Dokument, und Belege können genau zitiert werden.',
      'Teaser — ein kurzer, automatisch generierter Einstiegstext pro Dokument (schnelle erste Ebene).',
      'Rückführung — alle Ebenen schreibt riski in die Datenbank zurück; die Suche arbeitet über Chunks und Teaser, die Volltexte bleiben abrufbar.',
    ],
  },
  {
    id: 'anreicherungen',
    title: 'Anreicherungen (Enrichments)',
    paragraphs: [
      'Über Suche hinaus verleiht riski den Dokumenten Struktur:',
    ],
    bullets: [
      'Georeferenzen — Straßen und Stadtteile, die in Dokumenten und Tagesordnungspunkten genannt werden, werden verknüpft und geo-kodiert (Grundlage der Karte). Adressblock-Fundstellen (Briefköpfe, Kontaktzeilen) filtert ein zweistufiges Verfahren heraus: ein deterministischer Adresszeilen-Check plus ein LLM-Gütegate, damit nur inhaltlich gemeinte Nennungen auf der Karte landen.',
      'Dokumenttyp-Tags — Beschlussvorlage, Anfrage, Antrag u. a. werden aus Papertyp, Namensmustern und (falls nötig) Teasern abgeleitet.',
      'Namens-Vektoren — Einbettungen für die Namen aller OParl-Objekte (Grundlage des semantischen Netzwerks).',
    ],
  },
  {
    id: 'ergebnis',
    title: 'Ergebnis-Zusammenfassung (query-guided)',
    paragraphs: [
      'Auf die Treffermenge Ihrer Frage läuft eine fragegeleitete Zusammenfassung: ein Sprachmodell fasst ALLE gefundenen Dokumente bezogen auf Ihre Frage zusammen — mit nummerierter Dokumentenliste, Berücksichtigungsvermerk pro Dokument und Angabe, welche Dokumente nicht berücksichtigt wurden.',
      'Dazu entstehen auf einen Schlag: das Netzwerk der beteiligten OParl-Objekte, die Zeitachse der Ereignisse und die Karte der genannten Orte. Ergebnisse werden stufenweise geladen: Dokumentenliste sofort, Zeitachse und Netzwerk folgen, die Zusammenfassung wird nachgereicht.',
      'Sie können die Antwort verfeinern („Verfeinern“ = Zusammenfassung mit Volltexten neu erzeugen) und einzelne Dokumente abwählen — Netzwerk, Karte und Zusammenfassung passen sich sofort an.',
    ],
    bullets: [],
  },
  {
    id: 'interaktion',
    title: 'So interagieren Sie mit riski',
    paragraphs: ['Die Seite „Das RIS“ bündelt alles hinter einer Suchzeile:'],
    bullets: [
      'Frage stellen — einfach in normalem Deutsch formulieren; auch Stichworte genügen (z. B. „theatersanierung“).',
      'Antwort lesen — die Zusammenfassung nennt jedes berücksichtigte Dokument mit Nummer; die Dokumentenliste darunter führt alle Treffer mit Download-Link.',
      'Dokumente steuern — Häkchen in der Liste abwählen oder setzen: Zusammenfassung, Karte und Netzwerk aktualisieren sich.',
      'Netzwerk erkunden — Knoten anklicken öffnet Details; per Klick lassen sich Nachbarn eines Knotens nachladen.',
      'Zeitachse und Karte — wann wurde was beraten und entschieden, und welche Orte sind betroffen.',
      'Verfeinern — für eine tiefere Antwort auf Basis der Volltexte.',
    ],
  },
];

const planned = {
  title: 'Ausblick: Wissen statt nur Suche',
  body: 'riski ist ein Forschungsprototyp — wir arbeiten an weiteren Funktionen. Insbesondere planen wir, strukturiertes Wissen aus den Dokumenten zu extrahieren, um die Suche schneller und zuverlässiger zu machen (Stichwort: Wissensgraph). Mehr dazu auf der Seite Wissen.',
};

// hash router owns location.hash — section jumps must scroll manually
// (href="#section" would navigate away to the home route)
function scrollTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}
</script>

<template>
  <div class="docs">
    <header class="docs-header">
      <h1>Dokumentation</h1>
      <p class="docs-sub">
        Was riski ist, wie es funktioniert und wie Sie es benutzen.
      </p>
    </header>

    <nav class="docs-toc" aria-label="Inhalt">
      <span class="toc-title">Inhalt</span>
      <a v-for="s in sections" :key="s.id" href="#/dokumentation" class="toc-link"
         @click.prevent="scrollTo(s.id)">{{ s.title }}</a>
    </nav>

    <section v-for="s in sections" :id="s.id" :key="s.id" class="docs-section">
      <h2>{{ s.title }}</h2>
      <p v-for="(p, i) in s.paragraphs" :key="`p${i}`">{{ p }}</p>
      <ul v-if="s.bullets.length" class="docs-list">
        <li v-for="(b, i) in s.bullets" :key="`b${i}`">
          <strong>{{ b.split(' — ')[0] }}</strong>{{ b.includes(' — ') ? ' — ' + b.split(' — ').slice(1).join(' — ') : '' }}
        </li>
      </ul>
    </section>

    <section class="docs-planned">
      <h2>{{ planned.title }}</h2>
      <p>{{ planned.body }}</p>
      <a href="#/wissen" class="planned-link" @click="$emit('navigate', '/wissen')">Zur Seite Wissen →</a>
    </section>
  </div>
</template>

<style scoped>
.docs {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #1f2937;
}

.docs-header {
  margin-bottom: 16px;
}

.docs-header h1 {
  margin: 0 0 6px;
  font-size: 1.6rem;
}

.docs-sub {
  margin: 0;
  color: #6b7280;
}

.docs-toc {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  align-items: center;
  padding: 14px 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  margin-bottom: 24px;
}

.toc-title {
  font-weight: 600;
  font-size: 0.88rem;
  color: #374151;
  margin-right: 4px;
}

.toc-link {
  font-size: 0.88rem;
  color: #667eea;
  text-decoration: none;
}

.toc-link:hover {
  text-decoration: underline;
}

.docs-section {
  scroll-margin-top: 90px;
  margin-bottom: 28px;
}

.docs-section h2 {
  font-size: 1.15rem;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid #667eea;
}

.docs-section p {
  margin: 0 0 10px;
  line-height: 1.65;
  font-size: 0.95rem;
}

.docs-list {
  margin: 0 0 10px;
  padding-left: 22px;
  line-height: 1.65;
  font-size: 0.95rem;
}

.docs-list li {
  margin-bottom: 6px;
}

.docs-planned {
  padding: 16px 18px;
  background: #f5f3ff;
  border: 1px solid #ddd6fe;
  border-radius: 10px;
}

.docs-planned h2 {
  font-size: 1.05rem;
  margin: 0 0 8px;
  border: none;
  padding: 0;
  color: #5b21b6;
}

.docs-planned p {
  margin: 0 0 8px;
  line-height: 1.6;
  font-size: 0.93rem;
}

.planned-link {
  color: #667eea;
  font-weight: 600;
  text-decoration: none;
  font-size: 0.93rem;
}

.planned-link:hover {
  text-decoration: underline;
}
</style>
