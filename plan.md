# Plan Neuer N8N-Verwalter

## Primärer Abschnitt: Aktuelle Programmstruktur und Funktionalität

### Anwendungseinstieg

- `einstieg.py` startet die Qt-Anwendung, lädt `style.qss` und öffnet `HauptFenster`.
- Die Anwendung ist aktuell als klassische Desktop-Oberfläche auf Basis von `PyQt6` aufgebaut.

### Hauptfenster und Navigation

- `Schnittstelle/haupt_fenster.py` baut das Hauptlayout aus `HorizontaleLeiste`, `VertikaleLeiste` und einem zentralen `QStackedWidget`.
- Die Navigation ist derzeit statisch und enthält genau zwei Seiten:
  - `Verwaltung`
  - `N8N`
- Der Seitenwechsel ist weiterhin indexbasiert.
- Die Seite `N8N` wird über `Schnittstelle/web_widget.py:ProgrammSeite` als `QWebEngineView` eingebettet.
- Die URL der Webansicht ist aktuell noch fest auf `http://localhost:5678` gesetzt.
- Für eingebettete Web-Dienstseiten gibt es noch keine Authentifizierungslogik.

### Verwaltungsseite

- `Schnittstelle/verwaltung/verwaltung_fenster.py` ist der Einstiegspunkt für die fachliche Verwaltungsansicht.
- Dort werden Projektpfad, `.env`-Pfad und Entwurfspfad `.env.draft.json` aufgebaut.
- `VerwaltungFenster` erzeugt eine Instanz von `Kern.compose.env:Umgebungsvariablen` und reicht sie an die Verwaltungskomponenten weiter.
- Zusätzlich startet `VerwaltungFenster` einen `QTimer`, der alle 5 Sekunden `ComposeWidget.aktualisiere_inhalt()` ausführt.

### Compose-Verwaltung

- `Schnittstelle/verwaltung/compose_widget.py` ist aktuell die zentrale Orchestrierung für Runtime-Aktionen und Darstellung.
- Das Widget besteht aus drei Bereichen:
  - `ContainerBereich`
  - `VolumenBereich`
  - `AusgabeBereich`
- `ContainerBereich` zeigt die bekannten Dienste, ihren Aktivierungsstatus, den zugeordneten Container und den aktuellen Status.
- Der Aktionsbutton im `ContainerBereich` schaltet abhängig vom Laufzustand zwischen `Start`, `Stop` und `Neustart`.
- Optionale Dienste werden automatisch als ausgewählt markiert, wenn laufende Container erkannt werden und der Nutzer diese Auswahl nicht manuell überschrieben hat.
- `VolumenBereich` listet die per `podman volume ls` gefundenen Volumen.
- `AusgabeBereich` zeigt aktuell die Logs des ausgewählten Containers.
- Die Auswahl für die Ausgabe ist derzeit nur auf Container aus dem `ContainerBereich` ausgelegt; ein übergreifendes Auswahlmodell für Container, Volumen oder "nichts ausgewählt" existiert noch nicht.

### Runtime und Persistenz

- `Kern/podman.py` enthält die Compose-bezogene Laufzeitlogik und die Statuspersistenz.
- Die Klasse `PodmanComposeStartKonfiguration` bündelt:
  - ausgewählte Dienste
  - Compose-Dateien
  - effektive Umgebungsvariablen
- `baue_startkonfiguration(...)` validiert Pflichtvariablen und baut daraus die Compose-Konfiguration für den Stack.
- `podman_compose_argumente(...)` erzeugt die finalen Argumente für `podman compose`.
- `prozessumgebung_fuer_konfiguration(...)` kombiniert Prozessumgebung und effektive Variablen.
- Die letzte Startkonfiguration und die gewählten Dienste werden in `.compose.state.json` gespeichert.
- `ComposeWidget` nutzt bereits `podman compose up` und `podman compose down`.
- Für Stop/Neustart gibt es einen Fallback über direkte `podman stop`- bzw. `podman rm`-Aufrufe, wenn keine gespeicherte Compose-Startkonfiguration vorliegt.
- Die Erkennung `konfiguration_geaendert` ist bereits vorhanden und vergleicht die gewünschte Konfiguration mit der zuletzt gespeicherten.
- Die Dienstauswahl wird bereits gespeichert, aber das Wiedereinlesen in die UI ist aktuell noch auskommentiert.

### Umgebungsvariablen und Einstellungen

- `Kern/compose/env.py` ist die zentrale Fachschicht für Umgebungsvariablen.
- Die Klasse `Umgebungsvariablen` verwaltet:
  - Zuordnung von Diensten zu Compose-Dateien
  - Extraktion von `${VARIABLE}`-Definitionen aus den Compose-Dateien
  - zusätzliche fachliche Variablendefinitionen pro Dienst
  - Compose-Standardwerte
  - Laden aus `.env`
  - Zwischenspeicherung in `.env.draft.json`
  - Validierung fehlender Pflichtvariablen
  - Bereitstellung effektiver Werte für den Compose-Start
- `Schnittstelle/verwaltung/einstellungen_dialog.py` arbeitet bereits ausschließlich über diese Objekt-API.
- Der Dialog ergänzt fehlende Variablen der aktuellen Dienstauswahl automatisch, erlaubt zusätzliche manuelle Variablen, speichert Änderungen laufend als Entwurf und schreibt erst beim Bestätigen nach `.env`.

### Aktuell abgebildete Dienste

- `n8n`
- `open-webui`
- `flowise`
- `langfuse`
- `neo4j`
- `minio`
- `searxng`
- `supabase`
- `ollama`

### Funktionaler Ist-Stand

- Die Anwendung kann den ausgewählten Compose-Stack starten, stoppen und bei Konfigurationsänderungen neu starten.
- Containerstatus, Volumenliste und Logausgabe werden zyklisch aktualisiert.
- Die Umgebungsvariablen der aktivierten Dienste werden zentral verwaltet und vor dem Start validiert.
- Die derzeitige Webintegration ist noch auf eine einzelne statische `N8N`-Seite beschränkt.
- Dienstmetadaten sind aktuell doppelt gepflegt:
  - in `Schnittstelle/verwaltung/verwaltung_fenster.py`
  - in `Schnittstelle/verwaltung/compose_widget.py`

## Sekundärer Abschnitt: Umsetzungspläne für vorhandene TODOs

### Gruppe 1: Dienstseiten-Konfiguration und Web-Authentifizierung

Bezug auf TODOs:

- `Schnittstelle/haupt_fenster.py`: `PORT aus dem umgebungskontext auslesen`
- `Schnittstelle/web_widget.py`: `Websiten auth einbauen`

Ziel:

- Web-Dienstseiten sollen nicht mehr auf hartcodierten URLs beruhen, sondern aus derselben Dienst- und Konfigurationslogik entstehen wie Compose-Start und Einstellungen.
- Web-Dienstseiten sollen optional eine Authentifizierung unterstützen, ohne dienstspezifische Sonderfälle direkt in `QWebEngineView` zu verteilen.

Umsetzungsplan:

1. Einen zentralen Dienstkatalog einführen, der pro Dienst mindestens Titel, Container-Aliase, Web-URL-Bausteine und optionalen Auth-Typ beschreibt.
2. Die URL-Auflösung aus `FensterLayout` herausziehen und in diesen Dienstkatalog oder eine kleine Hilfsschicht verlagern.
3. Die URL aus effektiven Umgebungswerten ableiten, damit Port- oder Host-Änderungen aus `.env` unmittelbar berücksichtigt werden können.
4. `ProgrammSeite` so umbauen, dass sie nicht nur eine rohe URL, sondern eine kleine Konfiguration für Zielseite und Authentifizierungsmodus erhält.
5. Eine Authentifizierungsschicht definieren, die mindestens die Modi `keine`, `basic` und `cookie/token-vorbelegt` sauber abbilden kann.
6. Fehlerfälle sichtbar in der UI machen, damit ungültige Zugangsdaten oder nicht auflösbare URLs nicht als leere Webansicht enden.

Abnahmekriterien:

- Im Hauptfenster gibt es keinen hartcodierten Dienstport mehr.
- Die Web-URL wird aus fachlicher Konfiguration und effektiven Umgebungswerten abgeleitet.
- `ProgrammSeite` bleibt generisch und enthält keine fest eingebauten Spezialfälle für einzelne Dienste.
- Fehlgeschlagene Authentifizierung und fehlerhafte URL-Auflösung sind für den Nutzer sichtbar.

### Gruppe 2: Einheitliches Auswahlmodell für Container und Ausgabe

Bezug auf TODOs:

- `Schnittstelle/verwaltung/compose_widget.py`: `einen Selektor definieren, der übergreifend eines aus entweder container oder volumen auswählt`
- `Schnittstelle/verwaltung/compose_widget.py`: `Das Ausgabe widget braucht daher links von aktualisieren einen Knopf zum abwählen der aktuellen auswahl`
- `Schnittstelle/verwaltung/compose_widget.py`: `da offenbar keine Volumenlog existent, beschränkt sich der Selektor auf container, die ausgabe ebenfalls`

Ziel:

- Die Ausgabe soll nicht mehr implizit nur vom aktuell markierten Container abhängen, sondern von einem klaren, zentralen Auswahlzustand für Container oder `keine Auswahl`.

Umsetzungsplan:

1. In `ComposeWidget` einen zentralen Auswahlzustand einführen, der genau einen Kontext abbildet:
   - `container`
   - `keine Auswahl`
2. `ContainerBereich` auf ein semantisches Auswahl-Signal umstellen, statt nur Containernamen direkt weiterzureichen.
3. `AusgabeBereich` um einen expliziten Button zum Aufheben der Auswahl erweitern; dieser sitzt links vom Aktualisieren-Button.
4. Die Aktualisierungslogik so umbauen, dass sie abhängig vom Container-Auswahlzustand den passenden Inhalt lädt.
5. Für den Zustand `keine Auswahl` einen klar definierten Standardinhalt festlegen, statt implizit auf den letzten Containerzustand zurückzufallen.

Abnahmekriterien:

- Es gibt genau eine zentrale Auswahlquelle für die Ausgabe.
- Die Ausgabe arbeitet ausschließlich mit Container-Auswahl oder `keine Auswahl`.
- Die Auswahl kann im `AusgabeBereich` explizit zurückgesetzt werden.
- Der angezeigte Inhalt folgt nachvollziehbar dem Container-Auswahlzustand statt versteckter Nebenwirkungen.

### Gruppe 3: ComposeWidget entflechten und vereinfachen

Bezug auf TODOs:

- `Schnittstelle/verwaltung/compose_widget.py`: `vereinfachen`

Ziel:

- `ComposeWidget` soll wieder ein UI-Orchestrator sein und nicht gleichzeitig Layout, Selektionszustand, Statusabbildung, Podman-Aufrufe, Compose-Lifecycle und Fehlertextverwaltung bündeln.

Umsetzungsplan:

1. Die Initialisierung in kleine Setup-Methoden aufteilen:
   - Status laden
   - Teilwidgets bauen
   - Splitter zusammensetzen
   - Signale verbinden
   - Anfangszustand anwenden
2. Podman-spezifische Befehlsausführung und Zeitlimits aus `ComposeWidget` in eine dedizierte Runtime-Hilfsschicht verschieben.
3. Die Abbildung von Podman-Rohdaten auf UI-Status separat kapseln, damit Darstellung und Datenermittlung voneinander getrennt werden.
4. Doppelte Signalverbindungen entfernen und nur noch einen klaren Aktualisierungsfluss pro Benutzeraktion zulassen.
5. Gemeinsame Hilfsmethoden für Start, Neustart und Stop einführen, damit Persistenz, Fehlerbehandlung und UI-Rückmeldung nicht mehrfach implementiert werden.
6. Das Einlesen der gespeicherten Dienstauswahl wieder aktivieren und an einen definierten Initialisierungsschritt binden.
7. Den Dienstkatalog an eine zentrale Stelle ziehen, damit `DIENSTE` nicht in mehreren Modulen parallel gepflegt wird.

Abnahmekriterien:

- `ComposeWidget` enthält überwiegend UI-Ablauf statt direkter Laufzeitdetails.
- Podman-Befehle und Statusmapping sind separat testbar oder mindestens separat lesbar gekapselt.
- Start-, Stop- und Neustartpfade teilen sich gemeinsame Logik.
- Die gespeicherte Dienstauswahl wird beim Öffnen der Verwaltungsseite wieder korrekt angewendet.

## Offene Punkte

### Kurzfristig

1. Web-Dienstseiten über einen zentralen Dienstkatalog statt über hartcodierte URLs aufbauen.
2. Authentifizierung für eingebettete Web-Dienstseiten ergänzen.
3. Einheitliches Auswahlmodell für Container, Volumen und Ausgabe definieren.
4. `ComposeWidget` strukturell entflechten.
5. Gespeicherte Dienstauswahl beim Start wieder in die UI laden.

### Mittelfristig

1. Navigation von Indexen auf stabile `page_id`-Werte umstellen.
2. Laufende oder aktivierte Dienste als dynamische Seiten ergänzen.
3. Dienstmetadaten zentralisieren und in UI, Runtime und Webintegration gemeinsam verwenden.
4. Zusätzliche Dienstseiten persistent im `QStackedWidget` halten.

### Langfristig

1. Eine eigene `PodmanRuntime` als klare Schicht etablieren.
2. Podman-Installation und Runtime-Verfügbarkeit aktiv prüfen.
3. Dienstspezifische Erreichbarkeit, Healthchecks und Installationsstatus ergänzen.
4. Supabase aus dem aktuellen Platzhalterzustand herausführen.

## Nächste konkrete Umsetzungsreihenfolge

1. Zentralen Dienstkatalog einführen und daraus URL, Container-Aliase und Web-Metadaten ableiten.
2. TODO-Gruppe 1 für Portauflösung und Web-Authentifizierung umsetzen.
3. TODO-Gruppe 2 für das neue Auswahlmodell und den Ausgabe-Reset umsetzen.
4. TODO-Gruppe 3 für die strukturelle Entflechtung von `ComposeWidget` umsetzen.
5. Danach Navigation und Dienstseiten auf dynamische `page_id`-basierte Seiten erweitern.

## Kritische Punkte

- Die Env-Verwaltung darf nicht wieder auf mehrere Module verteilt werden.
- Dienstmetadaten dürfen nicht dauerhaft doppelt in UI und Runtime gepflegt werden.
- Vor der Volumen-Ausgabe muss fachlich klar sein, was bei einer Volumen-Auswahl überhaupt angezeigt werden soll.
- Nicht gespeicherte Entwürfe dürfen den echten Compose-Start nicht unbemerkt verändern.
- Die Navigation darf nicht indexbasiert bleiben, sobald dynamische Dienstseiten hinzukommen.

## Ergebnis nach vollständiger Umsetzung

Nach der vollständigen Umsetzung arbeitet die Oberfläche so:

- Die Anwendung verwaltet Dienste, Compose-Konfiguration und Web-Dienstseiten aus einem gemeinsamen Dienstkatalog.
- Die Verwaltungsseite zeigt Container, Volumen und Ausgabe weiterhin in einer festen, klar getrennten Dreiteilung.
- Die Startkonfiguration wird aus Dienstauswahl und `Umgebungsvariablen` gebaut.
- Podman startet und stoppt die gewählten Stacks über Compose.
- Web-Dienstseiten verwenden die effektive Konfiguration und können bei Bedarf authentifiziert geladen werden.
- Die Ausgabe folgt einem eindeutigen Auswahlmodell für Container, Volumen oder eine bewusst definierte Standardansicht.
- Zusätzliche Dienstseiten können später ohne indexbasierte Sonderlogik in die Navigation aufgenommen werden.
