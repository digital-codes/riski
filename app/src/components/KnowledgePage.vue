<script setup>
// change: site-menu — Wissensseite: Zukunftsperspektive des Projekts
// (Wissensextraktion / Wissensgraph). Bewusst eine kurze Teaser-Seite.
</script>

<template>
  <div class="knowledge">
    <header class="knowledge-header">
      <h1>Wissen</h1>
      <p class="knowledge-sub">Die nächste Stufe von riski.</p>
    </header>

    <section class="knowledge-card">
      <span class="badge">Zukünftige Arbeit</span>
      <h2>Hier entsteht der Wissensgraph von riski</h2>
      <p>
        Heute beantwortet riski Fragen, indem es Dokumente findet und deren
        Inhalte zusammenfasst. Der nächste Schritt: riski soll aus den
        Dokumenten selbst <strong>strukturiertes Wissen extrahieren</strong> —
        wer beteiligt war, was wann wo beschlossen wurde, wie Akteure, Orte
        und Themen zusammenhängen — und dieses Wissen dauerhaft als
        Wissensgraph bereitstellen.
      </p>
      <p>
        Ziel: eine Suche, die <strong>schneller und zuverlässiger</strong>
        wird — direkte Antworten statt Dokumentlisten, nachvollziehbare
        Zusammenhänge statt Trefferlisten. Die Dokumentation gibt einen
        ersten Ausblick auf dieses Vorhaben.
      </p>
      <p class="stay-tuned">Bleiben Sie dran.</p>
      <a href="#/dokumentation" class="back-link" @click="$emit('navigate', '/dokumentation')">← Zur Dokumentation</a>
    </section>

    <section class="knowledge-card related">
      <h2>Verwandte Ansätze</h2>
      <p>
        Wir schauen regelmäßig, wie andere RAG-Systeme dieses Problem
        angehen:
      </p>
      <ul>
        <li>
          <a href="https://github.com/HKUDS/LightRAG" target="_blank" rel="noopener noreferrer">LightRAG</a>
          (HKUDS, <a href="https://arxiv.org/abs/2410.05779" target="_blank" rel="noopener noreferrer">arXiv 2410.05779</a>) —
          graph-basiertes RAG: Entitäten und Beziehungen werden per LLM aus
          den Texten extrahiert und als Wissensgraph neben den Vektor-
          Index gestellt („dual-level retrieval“). Damit verfolgt LightRAG
          eine ähnliche Richtung wie unser Netzwerk- und Belegansatz —
          löst aber nicht die Kernschwierigkeit, aus unstrukturierten,
          realen Ratsdokumenten ein <em>zuverlässiges</em> Graphen-Wissen zu
          gewinnen. Genau daran arbeiten wir: Unser Graph entsteht zuerst
          aus der autoritativen OParl-Struktur, die Dokumentenanalyse soll
          ihn schrittweise um geprüftes Wissen erweitern.
        </li>
        <li>
          <a href="https://microsoft.github.io/graphrag/" target="_blank" rel="noopener noreferrer">Microsoft GraphRAG</a> —
          der ursprüngliche Referenzansatz für Community-basierte
          Wissensgraph-RAG-Systeme, auf den sich LightRAG als schlanke
          Alternative bezieht.
        </li>
      </ul>
      <p class="related-note">
        Auch bei den RIS-Zugängen schauen wir uns ab, was funktioniert
        (Details siehe <a href="#/dokumentation" class="inline-link" @click="$emit('navigate', '/dokumentation')">Dokumentation</a>):
        der offizielle
        <a href="https://sitzungskalender.karlsruhe.de/db/ratsinformation/start" target="_blank" rel="noopener noreferrer">Sitzungskalender der Stadt Karlsruhe</a>,
        das <a href="https://maxliesegang.github.io/karlsruhe-oparl-viewer/" target="_blank" rel="noopener noreferrer">GemeinderatsRadar</a>
        (Vorlagen-Browse, Filter, Feeds) und das
        <a href="https://dis.delphi.tools" target="_blank" rel="noopener noreferrer">Desinformationssystem</a>
        (Volltext-Facetten, Abstimmungs-Erkennung).
      </p>
    </section>
  </div>
</template>

<style scoped>
.knowledge {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #1f2937;
}

.knowledge-header {
  margin-bottom: 16px;
}

.knowledge-header h1 {
  margin: 0 0 6px;
  font-size: 1.6rem;
}

.knowledge-sub {
  margin: 0;
  color: #6b7280;
}

.knowledge-card {
  padding: 20px 22px;
  background: #f5f3ff;
  border: 1px solid #ddd6fe;
  border-radius: 12px;
}

.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  background: #ede9fe;
  color: #5b21b6;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 12px;
}

.knowledge-card h2 {
  font-size: 1.15rem;
  margin: 0 0 12px;
}

.knowledge-card p {
  margin: 0 0 12px;
  line-height: 1.65;
  font-size: 0.95rem;
}

.stay-tuned {
  font-weight: 600;
  color: #5b21b6;
}

.knowledge-card.related {
  margin-top: 20px;
  background: #fff;
  border-color: #e5e7eb;
}

.knowledge-card.related h2 {
  font-size: 1.05rem;
}

.knowledge-card.related ul {
  margin: 0 0 12px;
  padding-left: 20px;
  line-height: 1.65;
  font-size: 0.93rem;
}

.knowledge-card.related li {
  margin-bottom: 10px;
}

.knowledge-card.related a {
  color: #667eea;
}

.related-note {
  color: #6b7280;
  font-size: 0.9rem;
}

.inline-link {
  color: #667eea;
}

.back-link {
  color: #667eea;
  font-weight: 600;
  text-decoration: none;
  font-size: 0.93rem;
}

.back-link:hover {
  text-decoration: underline;
}
</style>
