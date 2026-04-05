# Plan Neuer N8N-Verwalter

## Aktueller Stand

Die Anwendung besitzt bereits eine lauffähige Verwaltungsseite in Qt:

- `ui/verwaltung_fenster.py` bündelt Container-, Volumen- und Logansicht.
- `ui/verwaltung/container.py` zeigt Dienste, Aktivierung und Start/Stop/Neustart.
- `ui/verwaltung/einstellungen_dialog.py` öffnet die Bearbeitung der Umgebungsvariablen.

Die Verwaltung der Umgebungsvariablen ist jetzt zentralisiert:

- `compose/env.py` enthält die Klasse `Umgebungsvariablen`.
- Diese Klasse ist die einzige Stelle für:
  - Definition der dienstbezogenen Variablen
  - Standardwerte
  - Laden von `.env`
  - Zwischenspeicherung in `.env.draft.json`
  - Validierung fehlender Pflichtvariablen
  - Bereitstellung effektiver Werte für den Compose-Start

Der Datenfluss ist damit durchgängig:

1. `VerwaltungFenster` erzeugt eine Instanz von `Umgebungsvariablen`.
2. Diese Instanz wird an `EinstellungenDialog` weitergereicht.
3. Der Dialog liest und schreibt keine `.env`-Datei mehr selbst.
4. `compose/podman.py` erhält dieselbe Instanz, um die Startkonfiguration zu bauen.

## Zielbild

Die Anwendung bleibt eine klassische Qt-Oberfläche mit drei festen Bereichen:

- `HorizontaleLeiste`: Kopfzeile mit Titel und Navigationstoggle
- `VertikaleLeiste`: Navigation
- zentrales Widget: Verwalter oder Dienst-UI

Die `HorizontaleLeiste` enthält keine Tabs und keine Seitenlogik.

## Fachliche Leitlinien

### Runtime

- Es wird ausschließlich `podman` unterstützt.
- Die UI soll nicht direkt mit Compose-Dateien oder `.env`-Dateien arbeiten.
- UI und Runtime sprechen über klar getrennte Anwendungsobjekte.

### Dienste

- `n8n` bleibt Pflichtdienst.
- Alle anderen Dienste sind optional.
- Die Auswahl erfolgt pro Dienst.
- Ollama-Profile bleiben als spätere Erweiterung vorgesehen.

### Umgebungsvariablen

Die Klasse `compose/env.py:Umgebungsvariablen` ist die zentrale Fachinstanz für Variablen.

Verantwortlichkeiten:

- Zuordnung von Diensten zu relevanten Compose-Dateien
- Extraktion von `${VARIABLE}` aus Compose-Dateien
- Ergänzung zusätzlicher fachlicher Variablen, die nicht als `${...}` im YAML stehen
- Definition von Standardwerten
- Laden von gespeicherten Werten aus `.env`
- Zwischenspeicherung nicht gespeicherter Änderungen
- Validierung vor dem Start
- Bereitstellung effektiver Umgebungswerte für Compose

Folgerung:

- `ui/verwaltung/einstellungen_dialog.py` kennt nur noch die Objekt-API
- `compose/podman.py` baut Startkonfigurationen auf Basis dieser Klasse
- weitere Module sollen keine eigene `.env`-Logik mehr einführen

## Aktuelle Architektur

### 1. Verwaltungsseite

`ui/verwaltung_fenster.py` ist aktuell die Orchestrierung der Verwaltungsansicht.

Verantwortlichkeiten:

- Aufbau des Splits für Container, Volumen und Ausgabe
- periodische Statusaktualisierung
- Öffnen des Einstellungsdialogs
- Weitergabe der Env-Verwaltung
- Vorvalidierung der Startkonfiguration

### 2. Env-Verwaltung

`compose/env.py` enthält:

- `UmgebungsvariableDefinition`
- `Umgebungsvariable`
- `Umgebungsvariablen`

Diese Schicht ist bereits produktiv eingebunden und ersetzt die frühere verteilte Logik.

### 3. Podman-Startkonfiguration

`compose/podman.py` ist aktuell noch klein, aber fachlich korrekt geschnitten.

Der Einstiegspunkt ist:

- `baue_startkonfiguration(dienst_ids, env_verwaltung)`

Diese Funktion liefert:

- die Compose-Dateien für die Auswahl
- die effektiven Umgebungsvariablen

Außerdem blockiert sie Starts, wenn Pflichtvariablen fehlen.

## Bereits umgesetzt

- Einstellungen-Button in der Aktionsleiste
- modaler Dialog zur Bearbeitung der Umgebungsvariablen
- automatische Ergänzung fehlender Variablen abhängig von der Dienstauswahl
- Anzeige von Dienst, Variable, Wert und Status
- Entwurfsspeicherung in `.env.draft.json`
- Speichern nach `.env`
- zentrale Definition und Validierung der Variablen in `compose/env.py`
- Anbindung der Env-Klasse bis zur Startkonfiguration in `compose/podman.py`

## Offene Punkte

### Kurzfristig

1. Die aktuelle Startlogik arbeitet noch mit `podman start` auf vorhandenen Containern.
2. Der nächste Schritt ist die echte Compose-basierte Runtime:
   - `compose up`
   - `compose down`
   - Übergabe der von `Umgebungsvariablen` gelieferten Werte
3. Die Dienstauswahl selbst ist noch nicht persistent gespeichert.
4. Das Ollama-Profil ist noch nicht in die Verwaltungsseite integriert.

### Mittelfristig

1. `ui/haupt_fenster.py` auf strukturierte Navigation mit `page_id` umstellen.
2. Laufende aktivierte Dienste als dynamische Einträge in `ui/vertikale_leiste.py` ergänzen.
3. Dienstseiten persistent im zentralen `QStackedWidget` cachen.
4. Web-Dienstseiten von `ui/web_fenster.py` aus in wiederverwendbare Dienstseiten überführen.

### Langfristig

1. echte `PodmanRuntime` als eigene Schicht aufbauen
2. Podman-Installation prüfen und später aus der UI anstoßen
3. Supabase-Integration aus dem Platzhalterzustand lösen
4. Installationsstatus, Healthchecks und UI-Erreichbarkeit je Dienst ergänzen

## Umsetzungspläne für vorhandene TODOs

### 1. `Schnittstelle/web_widget.py`: Website-Authentifizierung einbauen

Ziel:

- Web-Dienstseiten sollen auch dann direkt in der Qt-Webansicht funktionieren, wenn der Dienst eine Anmeldung oder vorab gesetzte Session-Daten benötigt.

Umsetzungsplan:

1. Für Web-Dienste eine kleine Metadatenstruktur einführen, die URL, Port, optionalen Login-Typ und benötigte Variablen beschreibt.
2. Die Zugangsdaten nicht im `QWebEngineView` hinterlegen, sondern aus der bestehenden Einstellungs- und Umgebungsvariablen-Schicht beziehen.
3. In `ProgrammSeite` eine klar getrennte Auth-Schicht ergänzen:
   - Basic-Auth für einfache Dienste
   - Cookie- oder Token-Setzen für Web-UIs mit Session
   - später optional Formular-Login für Sonderfälle
4. Vor dem Laden der Zielseite zuerst die Authentifizierung ausführen und Fehlerzustände sichtbar an die UI zurückmelden.
5. Für nicht konfigurierte Zugangsdaten einen kontrollierten Fallback ergänzen, damit die Seite nicht still scheitert.

Abnahmekriterien:

- Zugangsdaten kommen ausschließlich aus Konfiguration oder Einstellungen.
- Eine fehlgeschlagene Anmeldung erzeugt eine sichtbare Fehlermeldung.
- Die Webansicht bleibt wiederverwendbar und enthält keine dienstspezifisch hartcodierten Spezialfälle.

### 2. `Schnittstelle/haupt_fenster.py`: Port aus dem Umgebungskontext auslesen

Ziel:

- Die Web-URL darf nicht mehr fest auf `5678` verdrahtet sein, sondern muss aus der aktiven Dienstkonfiguration ableitbar werden.

Umsetzungsplan:

1. Die Verantwortung für Host, Port und URL-Pfad aus `FensterLayout` herausziehen und in eine fachliche Dienstbeschreibung verlagern.
2. Für `n8n` und spätere Web-Dienste definieren, welche Umgebungsvariable oder welcher Standardwert den Port liefert.
3. Die effektive URL aus derselben Konfiguration ableiten, die auch für Compose-Start und Einstellungen verwendet wird.
4. Beim Aufbau der `ProgrammSeite` die berechnete URL injizieren, statt sie per Stringverkettung lokal zu erzeugen.
5. Für fehlende oder ungültige Portwerte eine validierte Fallback-Strategie ergänzen, inklusive Meldung in der Oberfläche.

Abnahmekriterien:

- Es gibt keinen hartcodierten Port mehr im Hauptfenster.
- Änderungen an relevanten Umgebungsvariablen wirken sich auf die Web-URL aus.
- Die URL-Auflösung ist für weitere Dienste wiederverwendbar.

### 3. `Schnittstelle/verwaltung/compose_widget.py`: Widget vereinfachen

Ziel:

- `ComposeWidget` soll wieder klar lesbar werden und nur noch UI-Orchestrierung enthalten, nicht gleichzeitig Runtime-, Mapping- und Persistenzlogik.

Umsetzungsplan:

1. Die Initialisierung in kleine private Setup-Methoden aufteilen:
   - Status laden
   - Teilwidgets erzeugen
   - Splitter aufbauen
   - Signale verbinden
   - Anfangszustand anwenden
2. Laufzeitnahe Podman-Operationen in eine eigene Runtime-Hilfsschicht verschieben, damit `ComposeWidget` nicht selbst Befehle, Timeouts und Fehlertexte verwaltet.
3. Die Statusabbildung von Podman-JSON auf Dienststatus in eine separate Funktion oder Klasse auslagern, damit Darstellung und Datenermittlung getrennt bleiben.
4. Zustandsfelder wie ausgewählte Dienste, letzte Startkonfiguration, letzter Fehler und ausgewählter Container an einer Stelle zentral initialisieren.
5. Doppelte Signalverbindungen und redundante Aktualisierungswege entfernen, damit jede Benutzeraktion nur noch einen klaren Fluss auslöst.
6. Für Start, Neustart und Stop gemeinsame Hilfsmethoden einführen, damit Compose-Aufrufe, Persistenz und UI-Rückmeldungen nicht mehrfach implementiert werden.

Abnahmekriterien:

- `ComposeWidget` konzentriert sich auf UI-Ablauf und Delegation.
- Podman-spezifische Details sind außerhalb des Widgets gekapselt.
- Start-, Neustart- und Stop-Logik teilen sich gemeinsame Pfade statt duplizierten Code.

## Nächste konkrete Umsetzungsreihenfolge

1. Compose-Start und Compose-Stop in `compose/podman.py` und `ui/verwaltung_fenster.py` umsetzen.
2. Dienstauswahl und spätere Laufzeitoptionen persistent speichern.
3. Service-Katalog als eigene fachliche Struktur einführen.
4. `ui/haupt_fenster.py` und `ui/vertikale_leiste.py` auf dynamische Navigation umbauen.
5. Persistente Dienstseiten für Web- und native UIs ergänzen.

## Kritische Punkte

- Die Env-Verwaltung darf nicht wieder auf mehrere UI- oder Runtime-Dateien verteilt werden.
- Nicht gespeicherte Entwürfe dürfen den echten Compose-Start nicht unbemerkt verändern.
- Die Navigation darf nicht indexbasiert bleiben, sobald dynamische Seiten hinzukommen.
- Supabase ist weiterhin nur als Platzhalter vorhanden und blockiert einen vollständigen Stack-Aufbau.

## Ergebnis nach vollständiger Umsetzung

Nach der vollständigen Umsetzung arbeitet die Oberfläche so:

- links steht immer `Verwalter`
- im `Verwalter` wählt der Nutzer Dienste und bearbeitet deren Umgebungsvariablen
- die Startkonfiguration wird aus Dienstauswahl und `Umgebungsvariablen` gebaut
- Podman startet und stoppt die gewählten Stacks über Compose
- laufende aktivierte Dienste erscheinen zusätzlich in der Navigation
- ein Wechsel zwischen Seiten zerstört die Dienst-UI nicht
