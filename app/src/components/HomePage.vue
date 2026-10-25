<script setup>
import logo from '../assets/riski-logo.png';

defineEmits(['navigate']);
</script>

<template>
  <div class="home">
    <section class="hero">
      <img :src="logo" alt="riski Logo" class="hero-logo" />
      <h1 class="hero-title">riski</h1>
      <p class="hero-sub">
        Das Karlsruher Ratsinformationssystem — erklärt.
      </p>
      <a href="#/work" class="cta" @click="$emit('navigate', '/work')">
        Ratsinformationen erkunden
      </a>
    </section>

    <section class="section">
      <h2>Was ist riski?</h2>
      <p>
        riski macht den Zugriff auf den Karlsruher
        <a href="https://web1.karlsruhe.de/ris/oparl" target="_blank" rel="noopener">Ratsinformationssystems (RIS)</a>
        durchsuchbar und verständlich: Beschlüsse, Vorlagen, Sitzungen und
        Drucksachen des Gemeinderats werden aus dem offenen OParl-Portal
        geladen, mit KI-generierten deutschen Zusammenfassungen, Schlagwörtern
        und Ortsbezügen angereichert und semantisch durchsuchbar gemacht.
      </p>
      <div class="feature-grid">
        <div class="feature">
          <h3>Semantische Suche</h3>
          <p>
            Statt Stichwörtern versteht riski Fragen — hybride Suche über
            Volltext und Vektor-Embeddings findet auch, was nicht wörtlich
            im Text steht.
          </p>
        </div>
        <div class="feature">
          <h3>Netzwerkansicht</h3>
          <p>
            Vorlagen, Drucksachen, Gremien und Sitzungen als Graph —
            Zusammenhänge zwischen Akteuren und Themen auf einen Blick.
          </p>
        </div>
        <div class="feature">
          <h3>Zeitstrahl &amp; Karte</h3>
          <p>
            Wann und in welchem Kontext tauchte ein Thema im Rat auf? Der
            Zeitstrahl zeigt es; georeferenzierte Inhalte erscheinen auf
            einer Karte.
          </p>
        </div>
      </div>
    </section>

    <section class="section privacy-note">
      <h2>Datenschutz</h2>
      <p>
        Dies ist ein Forschungsprototyp. Es werden keine Tracking-Cookies
        gesetzt und keine Nutzungsprofile gebildet. Sucheinstellungen bleiben
        in Ihrem Browser (Sitzung); Anfragen werden zur Beantwortung an den
        Server übertragen. Details in der
        <a href="#/datenschutz" @click="$emit('navigate', '/datenschutz')">Datenschutzerklärung</a>.
      </p>
    </section>
  </div>
</template>

<style scoped>
.hero {
  text-align: center;
  padding: 64px 24px 48px;
}

.hero-logo {
  height: 96px;
  width: auto;
}

.hero-title {
  margin: 16px 0 8px;
  font-size: 2.75rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-sub {
  margin: 0 0 28px;
  font-size: 1.25rem;
  color: #4b5563;
}

.cta {
  display: inline-block;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  text-decoration: none;
  font-weight: 600;
  padding: 14px 32px;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.cta:hover {
  opacity: 0.92;
}

.section {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}

.section h2 {
  margin-top: 0;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin-top: 20px;
}

.feature {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 18px;
}

.feature h3 {
  margin: 0 0 8px;
  color: #667eea;
}

.feature p {
  margin: 0;
  font-size: 0.92rem;
  color: #4b5563;
}

.privacy-note {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
  margin-bottom: 24px;
}

.privacy-note h2 {
  color: #92400e;
}

@media (max-width: 768px) {
  .hero {
    padding: 40px 12px 32px;
  }

  .hero-title {
    font-size: 2rem;
  }

  .hero-sub {
    font-size: 1.05rem;
  }

  .section {
    padding: 16px 12px;
  }
}
</style>
