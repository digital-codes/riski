<script setup>
import { computed } from 'vue';

const props = defineProps({
  page: { type: String, required: true },
});

// computed (not setup-time): Vue reuses this component instance for both
// legal routes, so the page choice must react to prop changes
const isDatenschutz = computed(() => props.page === '/datenschutz');
</script>

<template>
  <div class="legal">
    <template v-if="isDatenschutz">
      <h1>Datenschutzerklärung</h1>
      <p class="proto-note">Hinweis: Platzhalter eines Forschungsprototyps.</p>

      <h2>Verantwortliche Stelle</h2>
      <p>
        Verantwortlich für dieses Angebot ist das Projekt riski (Kontakt siehe
        <a href="#/impressum">Impressum</a>).
      </p>

      <h2>Umfang der Datenerhebung</h2>
      <p>
        Dies ist ein Forschungsprototyp. Es werden keine Tracking-Cookies
        gesetzt, keine Nutzungsprofile gebildet und keine Analyse- oder
        Marketing-Dienste eingebunden. Beim Aufruf der Seiten verarbeitet der
        Server technisch notwendige Daten (u.&nbsp;a. IP-Adresse, Zeitpunkt)
        in Server-Logfiles, wie es für den Betrieb technisch erforderlich ist.
      </p>

      <h2>Suchanfragen</h2>
      <p>
        Suchanfragen und Suchsitzungen werden zur Beantwortung Ihrer Anfrage
        serverseitig verarbeitet und für die Dauer der Sitzung gespeichert.
        Die Inhalte der Suche stammen aus öffentlich zugänglichen
        OParl-Daten des Ratsinformationssystems der Stadt Karlsruhe.
      </p>

      <h2>Lokale Speicherung</h2>
      <p>
        Einstellungen (z.&nbsp;B. Suchsitzungs-Kennung) bleiben ausschließlich
        in Ihrem Browser und werden nicht serverseitig Ihrem Profil
        zugeordnet — ein Profil existiert nicht.
      </p>

      <h2>Ihre Rechte</h2>
      <p>
        Sie haben nach DSGVO das Recht auf Auskunft, Berichtigung, Löschung
        und Einschränkung der Verarbeitung. Wenden Sie sich hierzu an die im
        Impressum genannte Kontaktadresse.
      </p>
    </template>

    <template v-else>
      <h1>Impressum</h1>
      <p class="proto-note">Hinweis: Dummy-Angaben eines Forschungsprototyps.</p>

      <h2>Angaben gemäß § 5 DDG</h2>
      <p>
        riski — Forschungsprototyp<br />
        Musterstraße 12<br />
        76131 Karlsruhe<br />
        Deutschland
      </p>

      <h2>Kontakt</h2>
      <p>
        E-Mail: info@example.org<br />
      </p>

      <h2>Haftungshinweis</h2>
      <p>
        Die Inhalte dieses Prototyps werden mit großer Sorgfalt erstellt; für
        Richtigkeit, Vollständigkeit und Aktualität wird keine Gewähr
        übernommen. Datengrundlage sind öffentliche OParl-Daten des
        Ratsinformationssystems der Stadt Karlsruhe. Rechtsgültig sind
        ausschließlich die amtlichen Veröffentlichungen.
      </p>
    </template>
  </div>
</template>

<style scoped>
.legal {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 24px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  margin-top: 24px;
}

.legal h1 {
  margin-top: 0;
}

.legal h2 {
  font-size: 1.1rem;
  margin-bottom: 6px;
}

.legal p {
  color: #374151;
  line-height: 1.6;
}

.proto-note {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.85rem;
  color: #92400e;
}

@media (max-width: 768px) {
  .legal {
    margin-top: 12px;
    padding: 20px 12px;
  }
}
</style>
