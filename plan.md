# Plan Neuer N8N-Verwalter

## Zielbild

Die Anwendung bleibt eine klassische Qt-Oberfläche mit drei festen Bereichen:

- `HorizontaleLeiste`: nur Kopfzeile mit Logo, Titel und Button zum Ein-/Ausklappen der linken Navigation
- `VertikaleLeiste`: vollständige Navigation der Anwendung
- zentrales Widget: zeigt entweder den `Verwalter` oder die UI eines laufenden Dienstes

Die `HorizontaleLeiste` enthält **keine Tabs** und **keine Seitenlogik**.
Alle navigierbaren Einträge liegen ausschließlich in der `VertikaleLeiste`.

## Gewünschtes Verhalten

- Der Eintrag `Verwalter` ist immer vorhanden.
- Im `Verwalter` werden Dienste ausgewählt, installiert, gestartet, gestoppt und neu gestartet.
- Abhängig von den Einstellungen des Nutzers entstehen zusätzliche Einträge in der `VertikaleLeiste`.
- Diese zusätzlichen Einträge werden nur angezeigt, wenn der jeweilige Dienst:
  - aktiviert ist
  - eine darstellbare UI besitzt
  - aktuell läuft
- Beim Klick auf einen solchen Eintrag wird im zentralen Bereich nicht mehr der `Verwalter`, sondern die passende Dienst-UI angezeigt.
- Beim Wechsel zwischen Einträgen bleibt die Dienst-UI erhalten, damit keine erneute Anmeldung nötig ist.
- Beim Beenden der Anwendung dürfen Sessions verworfen werden.

## Fachliche Entscheidungen

### Container-Runtime

- Es wird ausschließlich `podman` unterstützt.
- Docker und Docker Compose werden nicht weiter als Zielarchitektur betrachtet.
- Die Anwendung prüft beim Start, ob `podman` vorhanden ist.
- Falls `podman` fehlt, soll die Installation aus der UI heraus angestoßen werden.
- Die eigentliche Nutzung der Anwendung soll möglichst universell sein.
- Die Installationslogik muss trotzdem plattformspezifisch behandelt werden.

### Dienste

- `n8n` ist Pflichtbestandteil und darf nicht abgewählt werden.
- Alle anderen Dienste sind optional.
- Die Auswahl erfolgt pro Dienst, nicht über Presets.
- CPU- und GPU-Varianten für Ollama bleiben erhalten und werden im `Verwalter` auswählbar gemacht.
- `Graphiti` wird im neuen Verwalter nicht berücksichtigt.

### Web- und Native-Seiten

Folgende Dienste gelten initial als eigenständige Seiten in der linken Navigation:

- `n8n`
- `Open WebUI`
- `Flowise`
- `Langfuse`
- `Neo4j`
- `MinIO`
- `SearXNG`
- `Supabase Studio`
- `Ollama`

Für die meisten dieser Dienste wird im zentralen Bereich eine Weboberfläche angezeigt.
`Ollama` ist ein Sonderfall: dort ist statt einer Web-UI eine native Qt-Seite vorgesehen, auf der Modelle angezeigt, gelöscht und neu gepullt werden können.

## Technische Leitidee

Die Anwendung bekommt eine zentrale Trennung zwischen:

- UI-Navigation
- Dienst-Konfiguration
- Laufzeitstatus
- Podman-Ausführung

Die UI darf nicht direkt mit `podman`-Kommandos oder Compose-Dateien verdrahtet sein.
Stattdessen arbeitet sie gegen klar getrennte Anwendungsobjekte.

## Zielarchitektur

### 1. Hauptfenster als Orchestrierung

`ui/haupt_fenster.py` wird die zentrale Koordinationsschicht.

Verantwortlichkeiten:

- Initialisierung von Runtime, Einstellungen und Service-Katalog
- Aufbau der festen Grundseiten
- Verwaltung der dynamischen Navigation
- Caching der Seiten im zentralen `QStackedWidget`
- periodische Statusaktualisierung
- Umschalten zwischen `Verwalter` und Dienstseiten

Das Hauptfenster verwaltet mindestens:

- `runtime`
- `service_catalog`
- `settings_store`
- `status_controller`
- `page_cache`
- `navigation_items`

### 2. HorizontaleLeiste

`ui/horizontale_leiste.py` bleibt schlank.

Verantwortlichkeiten:

- Logo anzeigen
- aktuellen Titel anzeigen
- linke Navigation ein- und ausklappen

Nicht enthalten:

- Tabs
- Seitenwechsel
- Dienstlogik
- Runtime-Logik

### 3. VertikaleLeiste als echte Navigation

`ui/vertikale_leiste.py` wird von einer simplen Textliste zu einer strukturierten Navigationsleiste umgebaut.

Ein Navigationseintrag benötigt mindestens:

- `id`
- `titel`
- `icon`
- `seiten_typ`
- `service_id` optional

Beispielhafte Eintragstypen:

- `verwalter`
- `web_ui`
- `native_ui`

Die Leiste zeigt immer:

- `Verwalter`

Die Leiste zeigt zusätzlich dynamisch:

- laufende aktivierte Dienste mit eigener Seite

Der Seitenwechsel darf nicht mehr über reine Listenindizes mit direktem `setCurrentIndex` gekoppelt sein.
Stattdessen muss über `nav_item.id` oder `page_id` auf gecachte Seiten gewechselt werden.

### 4. Zentrales Widget mit gecachten Seiten

Das zentrale `QStackedWidget` bleibt erhalten.
Es wird aber nicht mehr als Wegwerf-Container verwendet.

Stattdessen:

- die `Verwalter`-Seite wird einmal erzeugt
- jede Dienstseite wird bei erstem Zugriff erzeugt
- danach wird sie im Cache gehalten
- bei erneutem Wechsel wird dieselbe Instanz wieder angezeigt

Vorteil:

- offene Sessions bleiben beim Umschalten erhalten
- Browserzustand bleibt erhalten
- Seiten werden nicht unnötig neu geladen

## Seitenmodell

### Verwalter-Seite

Der `Verwalter` ist eine feste Seite im zentralen Widget.
Er bündelt die eigentliche Systemverwaltung.

Inhalt:

- Auswahl der aktivierten Dienste
- Auswahl des Ollama-Profils `cpu`, `gpu-nvidia`, `gpu-amd`
- Anzeige des Installationsstatus
- Anzeige des Laufzeitstatus
- Aktionen:
  - Installieren
  - Starten
  - Stoppen
  - Neustarten
  - optional Löschen

Die heute leeren Module können dafür genutzt werden:

- `ui/verwaltung/container.py` für Dienstauswahl und Aktionen
- `ui/verwaltung/ausgabe.py` für Prozess- und Podman-Ausgaben
- `ui/verwaltung/volumen.py` für Details, Ports, Images, Volumes und Laufzeitinformationen

Diese Module sollen keine separaten linken Navigationseinträge werden.
Sie bilden gemeinsam die feste `Verwalter`-Seite.

### Dienstseiten

Für jeden aktivierten und laufenden Dienst mit UI wird eine eigene Seite bereitgestellt.

Mögliche Varianten:

- Web-Seite über `QWebEngineView`
- native Qt-Seite für Spezialfälle wie `Ollama`

`ui/web_ui.py` wird zur Grundlage der persistenten Dienstseiten.
Die Klasse muss erweitert werden um:

- lazy loading
- optional gemeinsame `QWebEngineProfile`-Nutzung
- saubere Wiederverwendung derselben Instanz
- optional Auth-Handling

## Service-Katalog

Es wird ein zentraler Service-Katalog eingeführt.
Nicht mehr aus Tabellenzellen oder Portstrings ableiten.

Jeder Dienst erhält strukturierte Metadaten:

- `id`
- `titel`
- `compose_service_name`
- `pflichtdienst`
- `standard_aktiv`
- `hat_web_ui`
- `seiten_typ`
- `icon_path`
- `url_builder`
- `profile_abhaengig`
- `installationsrelevant`

Beispiel:

- `n8n`: Pflichtdienst, Web-UI
- `open-webui`: optional, Web-UI
- `ollama`: optional, native Seite

## Einstellungen

Die Nutzerauswahl wird persistent gespeichert.

Zu speichern sind mindestens:

- aktivierte Dienste
- Ollama-Profil
- optionale zusätzliche Laufzeitparameter

Diese Einstellungen beeinflussen:

- welche Compose-Overrides gebaut werden
- welche Dienste gestartet werden
- welche Einträge in der linken Navigation grundsätzlich entstehen dürfen

## Compose-Strategie

Die Legacy-Idee mit einem großen Compose-Block wird aufgelöst.

Geplant ist:

- Grund-Compose für Pflichtbestandteile
- einzelne dienstspezifische Override-Dateien
- beim Start werden aus den gewählten Diensten die passenden Overrides zusammengestellt

Dadurch wird die Konfiguration nutzerabhängig aufgebaut.

Supabase bleibt Bestandteil des Systems, aber die benötigten Compose-Dateien sollen direkt ins Projekt übernommen werden.
Der bisherige Git-Clone zur Laufzeit entfällt langfristig.

## Podman-Abstraktion

Es wird eine eigene Runtime-Schicht eingeführt, z.B. `PodmanRuntime`.

Verantwortlichkeiten:

- `podman` erkennen
- Installation prüfen
- `compose up`
- `compose down`
- Statusabfragen
- Logs lesen
- Container-Details lesen
- Images und Volumes verwalten
- Ollama-spezifische Kommandos ausführen

Die UI spricht nur mit dieser Runtime und nicht direkt mit Shell-Kommandos.

## Statuslogik

Die alte Statuslogik aus `legacy/LocalAI.py` bleibt inhaltlich nützlich, wird aber auf Podman übertragen.

Benötigte Informationen:

- läuft der Dienst
- welche Ports sind veröffentlicht
- ist die UI erreichbar
- welcher Eintrag darf in der Navigation erscheinen

Die Sichtbarkeitsregel für linke Diensteinträge lautet:

- Dienst ist aktiviert
- Dienst läuft
- Dienst hat eine darstellbare Seite

Optional kann zusätzlich die Erreichbarkeit geprüft werden, um Web-Einträge erst dann klickbar zu machen, wenn die UI tatsächlich antwortet.

## Datenfluss in der Anwendung

### Beim Start der Anwendung

1. Qt-Anwendung startet
2. `HauptFenster` lädt Einstellungen
3. `HauptFenster` initialisiert Runtime und Service-Katalog
4. `Verwalter`-Seite wird aufgebaut
5. `VertikaleLeiste` zeigt zunächst mindestens `Verwalter`
6. Statusabfrage läuft an
7. laufende aktivierte Dienste erzeugen zusätzliche linke Einträge

### Beim Ändern der Einstellungen

1. Nutzer aktiviert oder deaktiviert einen Dienst im `Verwalter`
2. Einstellungen werden gespeichert
3. laufende Navigation wird neu berechnet
4. ein Dienst erscheint erst als zusätzlicher Navigationseintrag, wenn er auch wirklich läuft

### Beim Starten von Diensten

1. Nutzer klickt im `Verwalter` auf Starten
2. Runtime baut die gewählten Compose-Dateien zusammen
3. Podman startet die Dienste
4. Statusabfrage erkennt laufende Dienste
5. `VertikaleLeiste` ergänzt neue Einträge
6. beim Anklicken wird die jeweilige Seite im zentralen Widget angezeigt

## Einbau in die aktuelle UI

### Hauptfenster

Die aktuelle Struktur von `ui/haupt_fenster.py` ist als Basis geeignet, benötigt aber folgende Umbauten:

- keine harte Verdrahtung von Listenindex auf `QStackedWidget`-Index
- Einführung eines Seiten-Caches
- Einführung strukturierter Navigation
- feste `Verwalter`-Seite anlegen
- dynamische Dienstseiten ergänzen
- Titel der `HorizontaleLeiste` abhängig vom aktiven Seiteneintrag setzen

### HorizontaleLeiste

Die vorhandene Klasse kann fast unverändert bleiben.
Sie braucht nur:

- Toggle der linken Leiste
- Anzeige des aktuellen Seitentitels

### VertikaleLeiste

Die vorhandene Klasse muss erweitert werden um:

- strukturierte Daten statt nur `list[str]`
- zuverlässige Icons pro Eintrag
- Zugriff auf `page_id`
- Neuaufbau der Liste ohne Verlust der aktiven Auswahl

### WebUI

`ui/web_ui.py` darf nicht nur stumpf `setUrl()` beim Erzeugen aufrufen.
Die Seite braucht:

- persistenten Zustand
- definierte Dienst-ID
- optional gemeinsames Browser-Profil
- spätere Erweiterbarkeit für Auth und Reachability

### Verwaltungsmodule

Die Dateien unter `ui/verwaltung/` sind der richtige Platz für die feste Verwaltungsseite.

Geplante Aufteilung:

- `container.py`: Dienste, Auswahl, Installationsstatus, Start/Stop/Restart
- `ausgabe.py`: globale Logs und Prozessausgaben
- `volumen.py`: Details, Ports, Container, Volumes, Images

## Empfohlene Umsetzungsreihenfolge

1. `VertikaleLeiste` auf strukturierte Navigation umbauen
2. `HauptFenster` auf `page_id`-basierte Navigation und Seiten-Cache umstellen
3. feste `Verwalter`-Seite aufbauen
4. `ui/web_ui.py` zu wiederverwendbaren Dienstseiten ausbauen
5. Service-Katalog einführen
6. Settings-Store einführen
7. `PodmanRuntime` einführen
8. Status-Polling und dynamische Navigation anbinden
9. Compose-Override-Bau pro ausgewähltem Dienst umsetzen
10. Podman-Installation aus der UI integrieren

## Kritische Punkte

- Die Nutzung kann plattformübergreifend sein, die automatische Installation von `podman` aber nicht.
- Deshalb muss die Installationslogik getrennt von der normalen Runtime behandelt werden.
- Die Navigation darf nicht indexbasiert bleiben, sonst brechen dynamische Einträge die Seitenzuordnung.
- Seiten im zentralen Widget dürfen nicht bei jedem Wechsel neu erzeugt oder entfernt werden.
- Supabase muss vor der eigentlichen Runtime-Migration aus der Git-Clone-Logik gelöst und ins Projekt integriert werden.

## Ergebnis nach Umsetzung

Nach der Umsetzung arbeitet die Oberfläche so:

- links steht immer `Verwalter`
- im `Verwalter` wählt der Nutzer Dienste und steuert Podman
- laufende aktivierte Dienste erscheinen automatisch als zusätzliche Einträge links
- ein Klick auf einen laufenden Dienst zeigt dessen UI im zentralen Bereich
- beim Zurückwechseln bleibt die zuvor geöffnete Dienst-UI erhalten
- die obere Leiste bleibt nur eine Kopfzeile und enthält keine Tabs
