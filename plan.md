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
