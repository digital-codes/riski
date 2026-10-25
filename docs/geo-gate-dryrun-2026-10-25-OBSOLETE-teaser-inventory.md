# pgGeoGateCleanup — DRY RUN (2026-10-25 07:49)

Permissive gate: only confident `boilerplate` verdicts hide a link; `unsure`/`content`/ungated stay visible.

## Streets_items_Files — 15608 rows to gate

[progress] Streets_items_Files: verdicts so far {"content": 597, "boilerplate": 73, "unsure": 0, "error": 0} (of 15608 rows)

### Removal candidates so far (73):
- Farnweg ← Anfrage Mai 2023 Dach Aussegnungshalle PV Anlage [[teaser] …halle PV Anlage CDU-Fraktion  im Ortschaftsrat  Stupferich  Farnweg 1 76228 Karlsruhe  CDU-Fraktion im Ortscha]
  reason: Die Straße wird ausschließlich in der Absenderadresse der CDU-Fraktion genannt, nicht im inhaltlichen Haupttext der Anfrage.
  context:
    Farnweg 1 76228 Karlsruhe
- Karl-Friedrich-Straße ← Tagesordnung ö [[teaser] …und Bauen  Immobilienmanagement  Flächenmanagement  Zoo    Karl-Friedrich-Straße 10, 76133 Karlsruhe  Telefon ]
  reason: Straße wird ausschließlich in der Adresse des Dezernats im Briefkopf genannt.
  context:
    Karl-Friedrich-Straße 10, 76133 Karlsruhe
- Marktplatz ← Protokoll TOP 21 [[teaser] …at der Gemeinderat Karlsruhe in einer Plenarsitzung auf dem Marktplatz zusammen, um den Ersatz eines defekten ]
  reason: Der Name erscheint ausschließlich im Metadaten-Bereich (Gremiumsangabe) und nicht im inhaltlichen Haupttext.
  context:
    **Gremium:** Gemeinderat Karlsruhe, Plenarsitzung am Marktplatz
- Zähringerstraße ← HGW_Badnerlandhalle_3gr02K01 [[teaser] …|   |   |   | | --- | --- | --- | --- | |  Stadt Karlsruhe Zähringerstraße 61 16133 Karlsruhe  |   |   |   | |]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Stadt Karlsruhe genannt, nicht im inhaltlichen Haupttext.
  context:
    |  Stadt Karlsruhe
    Zähringerstraße 61
    16133 Karlsruhe  |   |   |   |
- Zähringerstraße ← HGW_Badnerlandhalle_3si_K001 [[teaser] …|   |   |   | | --- | --- | --- | --- | |  Stadt Karlsruhe Zähringerstraße 61 16133 Karlsruhe  |   |   |   | |]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Stadt Karlsruhe genannt, nicht im inhaltlichen Haupttext.
  context:
    |  Stadt Karlsruhe
    Zähringerstraße 61
    16133 Karlsruhe  |   |   |   |
- Marktplatz ← Tagesordnung (öffentlich) Ausschuss/Ortschaftsrat [[teaser] …zungsantrag: CDU Vorlage: 2022/1068/4 - Vorberatung -  2.2. Marktplatz für die Zukunft mit Bäumen ausstatten E]
  reason: Der Name stammt aus dem Veranstaltungsort-Boilerplate (Bürgersaal, Rathaus am Marktplatz).
  context:
    Bürgersaal, Rathaus am Marktplatz
- Blütenweg ← Lageplan [[teaser] …rtenstadt Karlsruhe e.G.  Stadt Karlsruhe Liegenschaftsamt  Blütenweg 28  |  Maßstab: 1:500 bei DIN A4 | Gemar]
  reason: Die Straße wird ausschließlich im Adressblock des Liegenschaftsamts genannt, nicht im inhaltlichen Haupttext des Lageplans.
  context:
    Blütenweg 28
- Hebelstraße ← DHH 2011/2012: Antrag 139: GRÜNE: Waldklassenzimmer: Erhöhung der Mittel für Waldführungen im Jahr des Waldes [[teaser] …aldführungen im Jahr des Waldes GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 093: Die Linke: Zuschuss für kostenlose Betreuung von Kindern von Geringverdienern/-innen (SGB II, SGB XII, Wohngeld, Kinderzuschlag) in Kindertageseinrichtungen [[teaser] …eld, Kinderzuschlag) in Kindertageseinrichtungen Die Linke, Hebelstraße 13, 76133 Karlsruhe  DIE LINKE.  Herrn]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    Die Linke, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 135: GRÜNE: Erhöhung der Zuschüsse für den Tierschutzfonds [[teaser] …schüsse für den Tierschutzfonds GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 015: GRÜNE: Birkenhof: Betriebskostenzuschuss [[teaser] …rkenhof: Betriebskostenzuschuss GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 035: Die Linke: Independent Days Karlsruhe e. V. - Erhöhung des Zuschusses für das Unabhängige Filmfestival in der Schauburg [[teaser] …ür das Unabhängige Filmfestival in der Schauburg Die Linke, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    Die Linke, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 057: GRÜNE: ibz: Sommercamp "Freizeit erleben - Sprache fördern" [[teaser] …zeit erleben - Sprache fördern" GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 032: GRÜNE: Stärkung des Projektes "Schule und Kultur" [[teaser] …s Projektes "Schule und Kultur" GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 140: GRÜNE: Naturschutzzentrum: Zuschusserhöhung [[teaser] …schutzzentrum: Zuschusserhöhung GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 137: GRÜNE: Wirtschaftsförderung: Premiumworkshops [[teaser] ….2011  **Gremium, das die Sitzung oder Vorlage behandelt:** Hebelstraße 13, Gemeinderatsfraktion der Grünen, G]
  reason: Die Straße wird nur im Kontext der Adresse des Gremiums genannt, nicht im inhaltlichen Haupttext.
  context:
    **Gremium, das die Sitzung oder Vorlage behandelt:** Hebelstraße 13, Gemeinderatsfraktion der Grünen, Grundgesetz für Stadt und Land Baden-Württemberg (GGfuL), Bürgermeisterin Heinz Fenrich
- Hebelstraße ← DHH 2011/2012: Antrag 068: FDP: Änderung der "Grundsätze für die Förderung der freien Wohlfartspflege und freien Jugendhilfe" [[teaser] …d freien Jugendhilfe" FDP Fraktion Karlsruhe  FDP-Fraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der FDP-Fraktion genannt.
  context:
    FDP-Fraktion, Hebelstraße 13, 76133 Karlsruhe
- Marktplatz ← DHH 2011/2012: Antrag 068: FDP: Änderung der "Grundsätze für die Förderung der freien Wohlfartspflege und freien Jugendhilfe" [[teaser] …Karlsruhe  Herrn Oberbürgermeister  Heinz Fenrich  Rathaus, Marktplatz  76124 Karlsruhe  18.1.2011  # Änderung]
  reason: Der Platz wird nur im Briefkopf als Standort des Rathauses aufgeführt.
  context:
    Rathaus, Marktplatz
- Hebelstraße ← DHH 2011/2012: Antrag 017: GRÜNE: Fortsetzung Klimaschutzkampagne [[teaser] …Fortsetzung Klimaschutzkampagne GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 031: SPD: Streichung des Zuschusses für das Karlsruher Forum "Ethik in Recht und Technik" [[teaser] …orum "Ethik in Recht und Technik" SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 155: GRÜNE: Stadtarchiv - Umplanung der Aufstockung [[teaser] …hiv - Umplanung der Aufstockung GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 022: Freie Wähler: Zuschuss Sanierungskosten Vereinsheim DLRG [[teaser] …f des Doppelhaushaltsplans 2011/2012. Die Freien Wähler aus Hebelstraße 13 beantragen eine Zuschussvergabe von]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragsteller genannt, nicht im Haupttext des Antrags.
  context:
    Freie Wähler, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 101: KAL: Medizinische Versorgung Wohnsitzloser - Ausstattung von Behandlungsräumen [[teaser] …Ausstattung von Behandlungsräumen KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 006: GRÜNE: Bezahlung der TRK-Mitarbeiterin bei der Pressestelle durch die TechnologieRegion Karlsruhe [[teaser] …die TechnologieRegion Karlsruhe GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 142: GRÜNE: Stellenschaffung "Fachkraft energetische Sanierung" [[teaser] …chkraft energetische Sanierung" GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 125: GRÜNE: Verschieben der dynamischen Verkehrsinformation auf der Südtangente [[teaser] …information auf der Südtangente GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 061: KAL: Paritätische Sozialhilfe - Förderung von Wohnpartnerschaften [[teaser] …Förderung von Wohnpartnerschaften KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 007: SPD: Antrag auf Streichung der Stelleneinsparung beim Rechnungsprüfungsamt [[teaser] …sparung beim Rechnungsprüfungsamt SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 059: Die Linke: Internationales Begegnungszentrum (IBZ) - Zuweisung der Stelle von Herrn Kappler als feste Stelle des IBZ [[teaser] …telle von Herrn Kappler als feste Stelle des IBZ Die Linke, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird nur in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    Die Linke, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 085: GRÜNE: Karlsruher Pass - Erweiterung Bereich Gesundheit [[teaser] …Erweiterung Bereich Gesundheit GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  BÜNDNIS 90 DIE GRÜ]
  reason: Die Straße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 150: GRÜNE: Einstieg energetische Sanierung Rathaus am Marktplatz [[teaser] …instieg energetische Sanierung  GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 025: SPD: Kulturfonds Baden e. V.: Zuschussgewährung zur Unterstützung der Förderarbeit [[teaser] …ur Unterstützung der Förderarbeit SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 062: Freie Wähler: Miet- und Kautionszuschuss für das Straßenforum Karlsruhe [[teaser] …utionszuschuss für das Straßenforum Karlsruhe Freie Wähler, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Antragsteller genannt, nicht im Haupttext des Antrags.
  context:
    Freie Wähler, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 034: GRÜNE: Karlsruher Stummfilmtage - Zuschuss für Jubiläum im Jahr 2012 [[teaser] …chuss für Jubiläum im Jahr 2012 GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 089: GRÜNE: Stellenschaffung Koordinierungsstelle Schulsozialarbeit [[teaser] …ierungsstelle Schulsozialarbeit GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 138: Die Linke: Baden-Airpark, Investitionsfördermaßnahmen - Streichung [[teaser] …irpark, Investitionsfördermaßnahmen - Streichung Die Linke, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im Haupttext des Antrags.
  context:
    Die Linke, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 003: GRÜNE: Umstellung auf Recyclingpapier in der Stadtverwaltung [[teaser] …ngpapier in der Stadtverwaltung GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 004: GRÜNE: Supervision bei Tandems in Führungspositionen [[teaser] …i Tandems in Führungspositionen GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 117: CDU: Straßenausbesserung - Tiefbauamt [[teaser] …Straßenausbesserung - Tiefbauamt CDU Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerme]
  reason: Die Straße wird ausschließlich in der Absenderadresse der CDU-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    CDU Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 002: GRÜNE: Stärkung der Kommunalen Entwicklungszusammenarbeit [[teaser] …alen Entwicklungszusammenarbeit GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 060: SPD: Stellenschaffung - Eingliederungshilfe für behinderte Menschen [[teaser] …ungshilfe für behinderte Menschen SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Karlsruhe Gemeind]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 112: GRÜNE: Erhöhung der Investitionen in die Lärmminderung [[teaser] …estitionen in die Lärmminderung GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 047: GRÜNE: Finanzmittel für das Projekt Bildungsberatung des IB [[teaser] …Projekt Bildungsberatung des IB GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 090: GRÜNE: Zusätzliche Ausbildungsplätze im erzieherischen Bereich beim Stadtjugendausschuss [[teaser] …reich beim Stadtjugendausschuss GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 012: SPD: Stellenschaffung Umweltamt - Klimaschutz [[teaser] …schaffung Umweltamt - Klimaschutz SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 030: GRÜNE: Aufhebung der 5%igen Kürzung beim ZKM für 2012 [[teaser] …%igen Kürzung beim ZKM für 2012 GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 001: GRÜNE: Reduzierung des Kostenansatzes für repräsentative Jubiläumsveranstaltungen [[teaser] …tative Jubiläumsveranstaltungen GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 040: SPD: Unterstützung Barrierfreier Zugang in der Jüdischen Kultusgemeinde [[teaser] …g in der Jüdischen Kultusgemeinde SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext des Antrags.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 067: KAL: Globalzuschuss für Träger freiwilliger Leistungen [[teaser] …ür Träger freiwilliger Leistungen KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im Haupttext des Antrags.
  context:
    KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 021: Die Linke: Zuschuss für kostenloses Mittagessen an Kindertagesstätten und Schulen für Geringverdiener/-innen (SGB II, SGB XII, Wohngeld, Kinderzuschlag) [[teaser] …nnen (SGB II, SGB XII, Wohngeld, Kinderzuschlag) Die Linke, Hebelstraße 13, 76133 Karlsruhe  DIE LINKE.  Herrn]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    Die Linke, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 013: GRÜNE: Stellenschaffung Umweltamt - Koordination Gesundheit/Prävention [[teaser] …rdination Gesundheit/Prävention GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der GRÜNEN Gemeinderatsfraktion genannt, nicht im inhaltlichen Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 136: CDU: Stellenschaffung Wirtschaftsförderung [[teaser] …lenschaffung Wirtschaftsförderung CDU Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der CDU-Fraktion genannt, nicht im Haupttext des Antrags.
  context:
    CDU Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 141: GRÜNE: Sonderveranstaltungen zum Jahr der Wälder [[teaser] …nstaltungen zum Jahr der Wälder GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 026: SPD: Volkshochschule Karlsruhe - Erhöhung des Zuschusses für 2012 auf die Höhe von 2011 [[teaser] …es für 2012 auf die Höhe von 2011 SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der SPD-Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    SPD Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 033: GRÜNE: Kulturbereich: Projektförderung für interkulturelle Projekte [[teaser] …ng für interkulturelle Projekte GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext des Antrags.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← DHH 2011/2012: Antrag 016: GRÜNE: Stellenschaffung Umweltamt - Bereich Agenda 21, Öffentlichkeitsarbeit [[teaser] …genda 21, Öffentlichkeitsarbeit GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgerm]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Fraktion genannt, nicht im inhaltlichen Haupttext.
  context:
    GRÜNE Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Hebelstraße ← Antrag Linke_030 [[teaser] …Antrag Linke_030 Die Linke, mit Sitz in Karlsruhe (Hebelstraße 21, 76133), richtet einen Antrag an den Oberbür]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Antragstellerin genannt, nicht im inhaltlichen Haupttext.
  context:
    Die Linke, Hebelstraße 21, 76133 Karlsruhe
- Hebelstraße ← Anträge 354-355 SPD GRÜNE Stadtjugendausschuss Ausweitung Ferienangebote [[teaser] …e  **1. Autor der Präsentation:** SPD-Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe; GRÜNE-Gemeinderat]
  reason: Die Straße wird ausschließlich in den Absenderangaben der Fraktionen genannt, nicht im inhaltlichen Haupttext.
  context:
    **1. Autor der Präsentation:** SPD-Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe; GRÜNE-Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Markgrafenstraße ← Anlage A_1_Lebensraeume_final [[teaser] …## Auftraggeber: Stadt Karlsruhe  Umwelt und Arbeitsschutz  Markgrafenstraße 14  76124 Karlsruhe  0 500 1.000 ]
  reason: Die Straße wird ausschließlich im Adressblock des Auftraggebers genannt, nicht im inhaltlichen Haupttext.
  context:
    Markgrafenstraße 14
- Henriette-Obermüller-Straße ← Protokoll TOP 29 [[teaser] …, 15:30 Uhr öffentlich Ort: Südwerk-Bürgerzentrum Südstadt, Henriette-Obermüller-Straße 10, Karlsruhe Vorsitze]
  reason: Die Straße wird nur als Veranstaltungsort im Metadatenbereich (Ort der Sitzung) genannt, nicht im inhaltlichen Haupttext.
  context:
    öffentlich
    Ort: Südwerk-Bürgerzentrum Südstadt, Henriette-Obermüller-Straße 10, Karlsruhe
    Vorsitzende/r: Oberbürgermeister Dr. Frank Mentrup
- Hebelstraße ← Antrag Nr. 38 AfD - KEK Zuschüsse streichen [[teaser] …Antrag Nr. 38 AfD - KEK Zuschüsse streichen 38 AFD, Hebelstraße 13, 76133 Karlsruhe Herrn Oberbürgermeister Dr]
  reason: Die Hebelstraße wird ausschließlich in der Absenderadresse der AfD-Fraktion genannt, nicht im inhaltlichen Haupttext des Antrags.
  context:
    38
    AFD, Hebelstraße 13, 76133 Karlsruhe
    Herrn Oberbürgermeister
- Welfenstraße ← Anlage Einwohnerantrag [[teaser] …an folgende Adresse schicken:  ADFC Kreisverband Karlsruhe, Welfenstraße 13, 76137 Karlsruhe  # VERTRAUENSPERS]
  reason: Straße wird ausschließlich in der Absenderadresse des Antragstellers genannt.
  context:
    ADFC Kreisverband Karlsruhe, Welfenstraße 13, 76137 Karlsruhe
- Ostendstraße ← TOP 2 Anlage 2_Abgrenzung_Sanierungsgebiet [[teaser] …el Freier Stadtplaner BDA, SRL Freier Landschaftsarchitekt  Ostendstraße 106 70188 Stuttgart  fen (0711) 411 3]
  reason: Die Straße wird ausschließlich in der Adresse des externen Planers genannt, nicht im inhaltlichen Teil des Dokuments.
  context:
    Ostendstraße 106
    70188 Stuttgart
- Saarlandstraße ← Anlage 2 Luftbild [[teaser] …arlsruhe Liegenschaftsamt  |   |   | | --- | --- | --- | |  Saarlandstraße 67  |   |   | |  Maßstab: 1:500 bei]
  reason: Die Straße wird ausschließlich in der Absenderadresse des Liegenschaftsamts genannt, nicht im inhaltlichen Haupttext.
  context:
    | --- | --- | --- |
    |  Saarlandstraße 67  |   |   |
    |  Maßstab: 1:500 bei DIN A4 | Gemarkung Karlsruhe | Datum: 27.01.2025  |
- Niddastraße ← Tagesordnung Ausschuss/OV (öffentlich) [[teaser] …uli 2021, 19:00 Uhr,  Saal der Begegnungsstätte Grötzingen, Niddastraße 9, 76229 Karlsruhe  ## Öffentliche Sit]
  reason: Die Straße wird nur als Veranstaltungsort im Metadaten-Teil der Tagesordnung genannt.
  context:
    Saal der Begegnungsstätte Grötzingen, Niddastraße 9, 76229 Karlsruhe
- Hebelstraße ← Antrag CDU_014 [[teaser] …** 00.00.0000  **Gremium:** Gemeinderatsfraktion der CDU in Hebelstraße, Karlsruhe  **Thema des Berichts:** Po]
  reason: Die Hebelstraße wird nur im Kontext der Adresse des Gremiums (Absender-Metadaten) genannt, nicht im inhaltlichen Haupttext.
  context:
    **Gremium:** Gemeinderatsfraktion der CDU in Hebelstraße, Karlsruhe
- Steinstraße ← 02Lageplan [[teaser] …arlsruhe Liegenschaftsamt  |   |   | | --- | --- | --- | |  Steinstraße  |   |   | |  Maßstab: 1:750 bei DIN A]
  reason: Die Straße wird ausschließlich im Briefkopf des Liegenschaftsamts genannt, nicht im inhaltlichen Haupttext des Lageplans.
  context:
    | --- | --- | --- |
    |  Steinstraße  |   |   |
    |  Maßstab: 1:750 bei DIN A4 | Gemarkung Karlsruhe | Datum: 14.07.2023  |
- Steinstraße ← 03Luftbild [[teaser] …arlsruhe Liegenschaftsamt  |   |   | | --- | --- | --- | |  Steinstraße  |   |   | |  Mailstab: 1:750 - bei DI]
  reason: Die Straße wird ausschließlich im Briefkopf des Liegenschaftsamts der Stadt Karlsruhe genannt, nicht im inhaltlichen Haupttext.
  context:
    | --- | --- | --- |
    |  Steinstraße  |   |   |
    |  Mailstab: 1:750 - bei DIN AA | Gemarkung Karlsruhe | Datum: 14.07.2023  |
- Hebelstraße ← Antrag VOLT_012 [[teaser] …rn.  **Verfasser des Berichts:** Volt-Gemeinderatsfraktion, Hebelstraße 21, 76133 Karlsruhe - Fabian Gaukel - ]
  reason: Die Straße wird ausschließlich in der Absenderadresse der Verfasser des Berichts genannt.
  context:
    **Verfasser des Berichts:**
    Volt-Gemeinderatsfraktion, Hebelstraße 21, 76133 Karlsruhe
    - Fabian Gaukel
- Rathausstraße ← TOP 2: Anfrage_CDU_Wettersteinstraße_Original [[teaser] …erwaltung Wolfartsweier z. Hd. H. Ortsvorsteher Anton Huber Rathausstraße 2  76228 Karlsruhe  # Straßenbelag d]
  reason: Die Straße wird ausschließlich in der Empfängeradresse des Dokuments genannt.
  context:
    z. Hd. H. Ortsvorsteher Anton Huber
    Rathausstraße 2
- Niddastraße ← TOP 2 Protokollauszug [[teaser] …1 Uhr | Herbert-Schweizer-Haus Begegnungsstätte Grötzingen, Niddastraße 9, 76229 Karlsruhe  | |  Vorsitzende O]
  reason: Die Straße wird nur als Veranstaltungsort im Metadaten-Bereich des Protokolls genannt.
  context:
    |  öffentlich  |   |
    |  26. Juli 2023, 18 bis 21 Uhr | Herbert-Schweizer-Haus Begegnungsstätte Grötzingen, Niddastraße 9, 76229 Karlsruhe  |
    |  Vorsitzende Ortsvorsteherin Karen Eßrich  |   |
- Hebelstraße ← KAL-TOP 246 [[teaser] …KAL-TOP 246 KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe  Herrn Oberbürgermeister  Heinz Fenrich…]
  reason: Die Straße wird ausschließlich im Absender-Block der Antragstellerin genannt, nicht im Haupttext des Antrags.
  context:
    KAL Gemeinderatsfraktion, Hebelstraße 13, 76133 Karlsruhe
- Esslinger Straße ← Tagesordnung (öffentlich) Ausschuss/Ortschaftsrat [[teaser] …uli 2024, um 20:30 Uhr im Musiksaal der Heinz-Barth-Schule (Esslinger Straße 2, 76228 Karlsruhe) ein. Die Tage]
  reason: Die Straße wird ausschließlich als Veranstaltungsort im Metadaten-Bereich (Einladung) genannt, nicht im inhaltlichen Haupttext der Tagesordnung.
  context:
    Musiksaal der Heinz-Barth-Schule, Esslinger Straße 2, 76228 Karlsruhe
