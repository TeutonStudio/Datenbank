# Plan N8N-Verwalter

## Stand der Analyse

Stand: 2026-04-16
Grundlage: letzter Commit `62c7a14` (`Schnittstelle optimiert.`). Nicht committete Aenderungen in der Arbeitskopie wurden fuer diese Analyse bewusst nicht als Quelle verwendet.

Die Anwendung ist ein lokaler Desktop-Verwalter fuer einen Podman-Compose-basierten Dienstestack. Der Fokus liegt aktuell auf drei Bereichen:

- Verwaltung ausgewaehlter Dienste und ihrer Compose-Dateien.
- Start, Stop, Neustart, Statusanzeige, Volumenliste und Logausgabe ueber Podman.
- Einbettung der Weboberflaechen einzelner Dienste in die Qt-Anwendung.

Der Code ist funktionsfaehig, aber noch nicht sauber geschichtet. Dienstmetadaten, Web-URLs, Container-Aliase und Compose-Zuordnungen sind an mehreren Stellen verteilt. Die naechste Ausbaustufe sollte deshalb zuerst die Dienstdefinitionen zentralisieren, bevor weitere Dienste wie Matrix/Synapse dauerhaft aufgenommen werden.

## Programmstruktur

### Einstieg

- `einstieg.py` startet die PyQt6-Anwendung.
- Beim Start wird `style.qss` geladen.
- Danach wird `Schnittstelle.haupt_fenster:HauptFenster` erzeugt und angezeigt.

### Hauptfenster

- `Schnittstelle/haupt_fenster.py` definiert das Hauptlayout.
- `HauptFenster` besteht aus:
  - oberer Leiste `HorizontaleLeiste`
  - linker Navigation `VertikaleLeiste`
  - zentralem `QStackedWidget`
- Die Navigation wird aus `PROGRAMM_SEITEN` erzeugt.
- Der erste Eintrag ist die Verwaltungsseite.
- Weitere Eintraege sind Webseiten, die mit `ProgrammSeite` als `QWebEngineView` eingebettet werden.
- Die Web-URLs sind aktuell hartcodiert:
  - N8N: `http://localhost:5678`
  - Open WebUI: `http://localhost:8080`
  - Flowise: `http://localhost:3001`
  - Langfuse: `http://localhost:3000`
  - SearXNG: `http://localhost:8081`
  - Neo4j: `http://localhost:7474`
  - MinIO: `http://localhost:9011`
  - Immich: `http://localhost:2283`
  - Ollama: `http://localhost:11435`

### Webeinbettung

- `Schnittstelle/web_widget.py` enthaelt `ProgrammSeite`.
- `ProgrammSeite` ist aktuell nur ein duennes `QWebEngineView`-Wrapper-Widget.
- Die Klasse nimmt eine URL entgegen und laedt sie direkt.
- Authentifizierung, Fehlerseiten, Reload-Strategie und dynamische URL-Aufloesung fehlen noch.
- Die Datei enthaelt den TODO `Websiten auth einbauen`.

### Verwaltung

- `Schnittstelle/verwaltung/verwaltung_fenster.py` ist der Einstieg in die Verwaltungsseite.
- Dort werden folgende Pfade ermittelt:
  - Projektwurzel
  - `.env`
  - `.env.draft.json`
- `VerwaltungFenster` erzeugt `Kern.compose.env:Umgebungsvariablen`.
- Danach wird `ComposeWidget` erzeugt.
- Ein `QTimer` aktualisiert alle 5 Sekunden `ComposeWidget.aktualisiere_inhalt()`.
- In `verwaltung_fenster.py` existiert ebenfalls eine `DIENSTE`-Liste, die aktuell nicht die einzige Quelle fuer Dienstmetadaten ist.

### Compose-Verwaltung

- `Schnittstelle/verwaltung/compose_widget.py` ist der zentrale UI-Orchestrator fuer Podman und Compose.
- Das Widget besteht aus:
  - `ContainerBereich`
  - `VolumenBereich`
  - `AusgabeBereich`
- `ContainerBereich` zeigt bekannte Dienste, Aktivierungsstatus, Containername und Status.
- `VolumenBereich` zeigt Projekt-Volumen aus `podman volume ls`, gefiltert ueber `com.docker.compose.project=n8nanwendung`.
- `AusgabeBereich` zeigt Logs des aktuell ausgewaehlten Containers.
- Start, Stop und Neustart werden ueber Dialoge mit laufender Podman-Ausgabe ausgefuehrt.
- Die Klasse enthaelt noch viel Laufzeitlogik direkt im UI-Code:
  - Podman-Kommandos
  - JSON-Auswertung
  - Statusmapping
  - Prozessdialoge
  - Startkonfigurationsvergleich
  - Persistenzaktualisierung
- Die gespeicherte Dienstauswahl wird inzwischen wieder geladen und in der UI angewendet.

### Teilwidgets der Verwaltung

- `Schnittstelle/verwaltung/compose/container_widget.py`
  - definiert `DienstDefinition`
  - zeigt Dienste in einer Tabelle
  - verwaltet Checkbox-Auswahl
  - sendet Signale fuer Auswahl, Einstellungen, Aktualisierung und Start/Stop/Neustart
- `Schnittstelle/verwaltung/compose/volumen_widget.py`
  - zeigt die vom Compose-Projekt erzeugten Podman-Volumen
  - hat aktuell nur eine Aktualisieren-Aktion
  - hat keine fachliche Volumenauswahl fuer die Ausgabe
- `Schnittstelle/verwaltung/compose/ausgabe_widget.py`
  - zeigt Containerlogs
  - kennt aktuell nur Containername und Diensttitel
  - besitzt noch keinen Button zum Aufheben der Auswahl

### Env-Verwaltung

- `Kern/compose/env.py` ist die zentrale Fachschicht fuer Umgebungsvariablen.
- `Umgebungsvariablen` verwaltet:
  - Dienst-zu-Compose-Datei-Zuordnung
  - Extraktion von `${VARIABLE}`-Definitionen aus Compose-Dateien
  - zusaetzliche Variablendefinitionen pro Dienst
  - Standardwerte
  - Laden aus `.env`
  - Entwurfsspeicherung in `.env.draft.json`
  - Validierung fehlender Pflichtvariablen
  - effektive Werte fuer den Compose-Start
- Die Zuordnung ist derzeit in `DIENST_COMPOSE_DATEIEN` gepflegt.
- Fuer einzelne Dienste werden Hostname- oder Port-Variablen mit Standardwerten ergaenzt.
- Diese Fachschicht ist bereits der richtige Ort fuer Umgebungslogik, sollte aber nicht dauerhaft auch Dienstkatalog, Web-URL-Logik und UI-Metadaten alleine tragen.

### Podman-Laufzeit

- `Kern/podman.py` enthaelt die Compose-nahe Runtime-Logik.
- `PodmanComposeStartKonfiguration` buendelt:
  - Dienst-IDs
  - Compose-Dateien
  - effektive Umgebungsvariablen
  - Compose-Profile
- `baue_startkonfiguration(...)` validiert Pflichtvariablen und baut daraus die Startkonfiguration.
- `podman_compose_argumente(...)` erzeugt die Argumentliste fuer `podman compose`.
- `prozessumgebung_fuer_konfiguration(...)` erzeugt die Laufzeitumgebung.
- `PROJEKT_NAME` ist auf `n8nanwendung` gesetzt und wird fuer Compose-Aufrufe sowie die Volumenfilterung genutzt.
- `.compose.state.json` speichert:
  - letzte Startkonfiguration
  - ausgewaehlte Dienste
- Fuer Ollama wird aktuell automatisch das Profil `gpu-amd` gesetzt.

### Compose-Dateien

- `Kern/compose/compose.yml` ist eine leere Basisdatei mit `services: {}`.
- Die eigentlichen Dienste liegen in Override-Dateien.
- Vorhandene Override-Dateien:
  - `compose.override.n8n-db.yml`
  - `compose.override.n8n.yml`
  - `compose.override.open-webui.yml`
  - `compose.override.flowise.yml`
  - `compose.override.langfuse-postgres.yml`
  - `compose.override.clickhouse.yml`
  - `compose.override.redis.yml`
  - `compose.override.minio.yml`
  - `compose.override.langfuse.yml`
  - `compose.override.neo4j.yml`
  - `compose.override.qdrant.yml`
  - `compose.override.searxng.yml`
  - `compose.override.supabase.yml`
  - `compose.override.ollama.yml`
  - `compose.override.immich.yml`
  - `compose.override.private.yml`
  - `compose.override.public.yml`
- `Kern/compose/README.md` beschreibt die zusammensetzbare Nutzung mit `podman compose`.
- `compose.override.supabase.yml` ist laut README noch ein Platzhalter.

## Aktuell abgebildete Dienste

- `n8n`
- `open-webui`
- `flowise`
- `langfuse`
- `neo4j`
- `minio`
- `searxng`
- `supabase`
- `ollama`
- `immich`

Hinweis: `compose.override.qdrant.yml` existiert, ist aber noch nicht als eigener Dienst in `DIENSTE` oder `DIENST_COMPOSE_DATEIEN` sichtbar.

## Bewertung des aktuellen Zustands

### Funktioniert bereits

- Die Anwendung startet als PyQt6-Desktopprogramm.
- Die Verwaltung kann Dienste auswaehlen.
- Pflichtdienst `n8n` ist fest aktiviert.
- Ausgewaehlte Dienste werden persistiert.
- Compose-Startkonfigurationen werden gebaut und gespeichert.
- Podman-Containerstatus wird zyklisch geladen.
- Podman-Volumen werden projektbezogen angezeigt.
- Containerlogs werden fuer den selektierten Container angezeigt.
- Start, Stop und Neustart laufen ueber sichtbare Prozessdialoge.
- `.env` und Entwurfsdatei werden zentral ueber `Umgebungsvariablen` verwaltet.
- Mehrere Webdienste sind im Hauptfenster eingebettet.

### Strukturelle Schwachstellen

- Dienstmetadaten sind mehrfach gepflegt:
  - `Schnittstelle/haupt_fenster.py:PROGRAMM_SEITEN`
  - `Schnittstelle/verwaltung/compose_widget.py:DIENSTE`
  - `Schnittstelle/verwaltung/verwaltung_fenster.py:DIENSTE`
  - `Kern/compose/env.py:DIENST_COMPOSE_DATEIEN`
  - `Kern/compose/env.py:DIENST_ZUSAETZLICHE_DEFINITIONEN`
- Web-URLs sind hartcodiert und nicht aus `.env` oder Dienstdefinitionen abgeleitet.
- `ComposeWidget` ist zu gross und mischt UI, Runtime, Statusmapping und Persistenz.
- Prozessdialoge sind direkt in `compose_widget.py` eingebettet.
- Auswahlmodell und Logausgabe sind nur auf Container ausgelegt.
- Volumen haben keine echte Auswahl- oder Detailansicht.
- Es gibt noch keine Podman-Verfuegbarkeitspruefung vor der UI-Nutzung.
- Webseiten haben keine Authentifizierungs- oder Fehlerbehandlungsschicht.
- Die Navigation ist weiterhin indexbasiert.
- Persistente Containerdaten liegen im Projektbaum und fuehren teilweise zu Rechteproblemen bei Dateisuche/Git-Status.

## Umsetzungsplan

### 1. Zentralen Dienstkatalog einfuehren

Ziel:

- Alle Dienstmetadaten sollen an einer Stelle liegen.
- UI, Compose, Env-Verwaltung und Webseiten sollen dieselbe Quelle verwenden.

Umsetzung:

1. Neues Modul anlegen, zum Beispiel `Kern/dienste.py`.
2. Eine zentrale `DienstDefinition` oder `DienstKatalogEintrag` definieren mit:
   - `dienst_id`
   - `titel`
   - `pflichtdienst`
   - `container_namen`
   - `compose_dateien`
   - `profile`
   - `web_titel`
   - `web_aktiv`
   - `web_host_variable`
   - `web_standard_url` oder URL-Bausteine
   - `auth_modus`
3. `ContainerBereich`, `ComposeWidget`, `VerwaltungFenster`, `Umgebungsvariablen` und `HauptFenster` auf diesen Katalog umstellen.
4. Die doppelten `DIENSTE`-Listen entfernen.
5. `DIENST_COMPOSE_DATEIEN` und zusaetzliche Env-Definitionen entweder aus dem Katalog ableiten oder klar mit ihm verbinden.

Abnahmekriterien:

- Ein neuer Dienst muss nur noch an einer fachlichen Stelle registriert werden.
- Containerliste, Webnavigation, Compose-Dateien und Env-Definitionen bleiben konsistent.
- `verwaltung_fenster.py` enthaelt keine eigene `DIENSTE`-Liste mehr.

### 2. Web-URLs dynamisch aufloesen

Ziel:

- Webdienste sollen nicht mehr ueber hartcodierte localhost-URLs im Hauptfenster definiert werden.

Umsetzung:

1. URL-Aufloesung als kleine Fachfunktion oder Klasse einfuehren.
2. Effektive Env-Werte aus `Umgebungsvariablen` fuer Web-URLs nutzen.
3. Hostname-Variablen wie `WEBUI_HOSTNAME`, `FLOWISE_HOSTNAME`, `LANGFUSE_HOSTNAME`, `NEO4J_HOSTNAME`, `IMMICH_HOSTNAME`, `OLLAMA_HOSTNAME` auswerten.
4. Werte im Format `:PORT`, `HOST:PORT`, `http://HOST:PORT` normalisieren.
5. `PROGRAMM_SEITEN` durch dynamische Navigationseintraege aus dem Dienstkatalog ersetzen.
6. Fehler bei fehlenden oder ungueltigen URL-Werten sichtbar machen.

Abnahmekriterien:

- `haupt_fenster.py` enthaelt keine hartcodierten Dienstports mehr.
- Aenderungen in `.env` werden nach Neustart der Anwendung fuer Webseiten beruecksichtigt.
- Eine defekte URL erzeugt eine klare Meldung statt einer leeren Webansicht.

### 3. Web-Authentifizierung vorbereiten

Ziel:

- Eingebettete Weboberflaechen sollen Authentifizierung unterstuetzen, ohne Speziallogik in `ProgrammSeite` zu verteilen.

Umsetzung:

1. Im Dienstkatalog einen Auth-Modus definieren:
   - `keine`
   - `basic`
   - `formular/manuell`
   - spaeter `cookie/token`
2. `ProgrammSeite` von einer reinen URL-Klasse zu einer Webseitenkonfiguration umbauen.
3. Fehler- und Ladezustand in der Webansicht sichtbar machen.
4. Zugangsdaten nur aus `.env` oder expliziten Einstellungen lesen, nicht hartcodieren.
5. Pro Dienst dokumentieren, ob Auth in der Anwendung automatisiert werden soll oder bewusst im eingebetteten Webformular bleibt.

Abnahmekriterien:

- `ProgrammSeite` bleibt generisch.
- Authentifizierung ist konfigurierbar.
- Es gibt keine dienstspezifischen Sonderfaelle direkt in `QWebEngineView`.

### 4. ComposeWidget entflechten

Ziel:

- `ComposeWidget` soll UI-Orchestrator bleiben und nicht Runtime, Prozesssteuerung und Mapping gleichzeitig enthalten.

Umsetzung:

1. Prozessdialoge aus `compose_widget.py` auslagern, zum Beispiel nach `Schnittstelle/verwaltung/compose/prozess_dialog.py`.
2. Podman-Abfragen in eine Runtime-Klasse verschieben, zum Beispiel `Kern/runtime/podman_runtime.py`.
3. Statusmapping von Podman-Rohdaten auf Dienststatus separat kapseln.
4. Start, Stop und Neustart ueber gemeinsame Hilfsmethoden fuehren.
5. Dialogverwaltung und Button-Deaktivierung vereinheitlichen.
6. Doppelte Signalverbindungen in `ComposeWidget.__init__` entfernen.

Abnahmekriterien:

- `ComposeWidget` ist deutlich kleiner und hauptsaechlich fuer Signalfluss und UI-Zusammensetzung verantwortlich.
- Podman-Kommandos sind separat testbar oder mindestens separat lesbar.
- Start-, Stop- und Neustartpfade teilen gemeinsame Fehler- und Persistenzlogik.

### 5. Auswahlmodell fuer Ausgabe einfuehren

Ziel:

- Die Ausgabe soll einem expliziten Auswahlzustand folgen.

Umsetzung:

1. Einen Auswahltyp definieren:
   - `keine`
   - `container`
   - spaeter optional `volumen`
2. `ContainerBereich` soll einen semantischen Auswahlkontext senden.
3. `AusgabeBereich` bekommt links vom Aktualisieren-Button einen Button `Auswahl aufheben`.
4. Bei `keine` wird ein definierter Standardinhalt angezeigt.
5. Volumenauswahl erst aktivieren, wenn klar ist, welche fachliche Ausgabe fuer Volumen sinnvoll ist.

Abnahmekriterien:

- Es gibt genau eine zentrale Quelle fuer die Ausgabeselektion.
- Die Ausgabe faellt nicht mehr implizit auf alte Containerwerte zurueck.
- Die aktuelle Auswahl kann sichtbar aufgehoben werden.

### 6. Runtime- und Projekt-Hygiene verbessern

Ziel:

- Die Anwendung soll robuster auf lokale Runtime-Probleme reagieren.

Umsetzung:

1. Beim Start der Verwaltungsseite Podman-Verfuegbarkeit pruefen.
2. Podman-Compose-Verfuegbarkeit pruefen.
3. Rechteprobleme in persistenten Datenverzeichnissen nicht als Anwendungsfehler behandeln.
4. Persistente Dienstdaten konsequent aus Git heraushalten.
5. `.gitignore` um generierte Datenverzeichnisse wie `Kern/neo4j/`, `Kern/immich/`, `Kern/searxng/` und weitere Dienstdaten erweitern.

Abnahmekriterien:

- Fehlendes Podman wird frueh und eindeutig angezeigt.
- Dateisuche und Git-Status werden nicht durch Containerdaten gestoert.
- Laufzeitdaten bleiben getrennt von Quellcode und Planung.

## Zukunftsplanung

### Synapse und Matrix implementieren

Ziel:

- Der Stack soll um einen Matrix-Homeserver auf Basis von Synapse erweitert werden.
- Die Integration soll dieselben Mechanismen nutzen wie die vorhandenen Dienste:
  - zentraler Dienstkatalog
  - Compose-Override
  - Env-Verwaltung
  - Containerstatus
  - Web-/Adminseite, falls vorhanden
  - persistente Datenverzeichnisse
  - private/public Overlay-Strategie

Geplante Dienststruktur:

- Dienst-ID: `matrix-synapse`
- Anzeigename: `Matrix Synapse`
- Hauptcontainer: `synapse`
- Datenbank: eigener Postgres-Dienst, zum Beispiel `synapse-postgres`
- Persistenz:
  - `../matrix/synapse/data:/data`
  - `../matrix/postgres:/var/lib/postgresql/data`
- Interne Synapse-Ports:
  - Client-Server API: `8008`
  - optional Federation: `8448`
- Lokale private Veroeffentlichung:
  - Standard-Webwert zum Beispiel `MATRIX_SYNAPSE_HOSTNAME=:8010`
- Oeffentliche Veroeffentlichung:
  - ueber `compose.override.public.yml` oder spaeter Caddy/Reverse-Proxy
  - Servername und `.well-known/matrix/*` muessen dabei explizit beruecksichtigt werden.

Neue Compose-Dateien:

1. `Kern/compose/compose.override.matrix-postgres.yml`
   - Postgres fuer Synapse
   - Healthcheck
   - eigenes Volume oder Bind-Mount unter `../matrix/postgres`
   - Variablen:
     - `MATRIX_POSTGRES_DB`
     - `MATRIX_POSTGRES_USER`
     - `MATRIX_POSTGRES_PASSWORD`
2. `Kern/compose/compose.override.matrix-synapse.yml`
   - Synapse-Container
   - Abhaengigkeit von `synapse-postgres`
   - Mount fuer `/data`
   - lokale Portbindung fuer `8008`
   - optional Federation-Port
   - Variablen:
     - `MATRIX_SERVER_NAME`
     - `MATRIX_SYNAPSE_REPORT_STATS`
     - `MATRIX_SYNAPSE_REGISTRATION_SHARED_SECRET`
     - `MATRIX_SYNAPSE_MACAROON_SECRET_KEY`
     - `MATRIX_SYNAPSE_FORM_SECRET`
     - `MATRIX_SYNAPSE_SIGNING_KEY_PATH`
     - `MATRIX_SYNAPSE_HOSTNAME`

Initialisierung:

1. Einen vorbereitenden Schritt fuer Synapse-Konfiguration definieren.
2. Beim ersten Start muss `homeserver.yaml` erzeugt oder aus einer Vorlage generiert werden.
3. Die Generierung darf nicht bei jedem Start bestehende Konfiguration ueberschreiben.
4. Servername, Datenbankverbindung, Secrets und Public-Base-URL muessen aus `.env` kommen.
5. Signing-Key und Medien-/Upload-Daten muessen persistent unter `../matrix/synapse/data` bleiben.

Dienstkatalog-Erweiterung:

1. `matrix-synapse` in den zentralen Dienstkatalog aufnehmen.
2. Compose-Dateien zuordnen:
   - `compose.override.matrix-postgres.yml`
   - `compose.override.matrix-synapse.yml`
3. Container-Aliase zuordnen:
   - `synapse`
   - `matrix-synapse`
   - `synapse-postgres`
4. Webeintrag definieren:
   - Titel: `Matrix Synapse`
   - URL aus `MATRIX_SYNAPSE_HOSTNAME`
   - Auth-Modus: `keine` oder `formular/manuell`, weil Synapse selbst primaer API-Dienst ist.
5. Optional einen zweiten Matrix-Webclient-Dienst spaeter ergaenzen, zum Beispiel Element Web, damit die Matrix-Nutzung direkt in der Anwendung sichtbar ist.

Env-Verwaltung:

1. Pflichtvariablen fuer Matrix/Synapse ergaenzen:
   - `MATRIX_SERVER_NAME`
   - `MATRIX_POSTGRES_PASSWORD`
   - `MATRIX_SYNAPSE_REGISTRATION_SHARED_SECRET`
   - `MATRIX_SYNAPSE_MACAROON_SECRET_KEY`
   - `MATRIX_SYNAPSE_FORM_SECRET`
2. Standardwerte nur fuer ungefaehrliche lokale Werte setzen:
   - `MATRIX_POSTGRES_DB=synapse`
   - `MATRIX_POSTGRES_USER=synapse`
   - `MATRIX_SYNAPSE_REPORT_STATS=no`
   - `MATRIX_SYNAPSE_HOSTNAME=:8010`
3. Secrets muessen vom Nutzer gesetzt oder durch eine spaetere sichere Generatorfunktion erzeugt werden.
4. Der Einstellungen-Dialog muss diese Variablen automatisch anzeigen, sobald `matrix-synapse` ausgewaehlt ist.

UI-Integration:

1. Matrix/Synapse als optionalen Dienst in der Verwaltung anzeigen.
2. Status fuer Synapse und Postgres aus Container-Aliasen erkennen.
3. Logs fuer den Synapse-Container anzeigen.
4. Webnavigation nur aktivieren, wenn ein sinnvoller Endpunkt definiert ist.
5. Optional spaeter eigene Matrix-Detailseite bauen:
   - Servername
   - Registrierungsstatus
   - Federation-Hinweise
   - Link zu Admin/API-Dokumentation
   - Link zu Element Web, falls installiert

Public/Federation-Planung:

1. Matrix muss fuer echte Nutzung sauber zwischen lokalem Testbetrieb und oeffentlichem Betrieb unterscheiden.
2. Fuer oeffentlichen Betrieb werden benoetigt:
   - stabiler `MATRIX_SERVER_NAME`
   - TLS ueber Reverse Proxy
   - Client-API unter `https://<server>/_matrix`
   - Federation unter `8448` oder per Delegation
   - `.well-known/matrix/server`
   - `.well-known/matrix/client`
3. Diese Konfiguration gehoert nicht hart in die private lokale Compose-Datei, sondern in ein klares Public-Overlay.

Abnahmekriterien:

- `matrix-synapse` kann als optionaler Dienst ausgewaehlt werden.
- Die notwendigen Env-Variablen erscheinen im Einstellungen-Dialog.
- `podman compose` startet Synapse mit Postgres.
- Synapse-Daten, Konfiguration und Signing-Key bleiben persistent.
- Containerstatus und Logs erscheinen in der Verwaltung.
- Private lokale Nutzung funktioniert ohne Public-Overlay.
- Oeffentliche Federation ist planerisch vorbereitet, aber nur aktiv, wenn Public-Konfiguration gesetzt ist.

### Weitere geplante Dienste und Ausbauten

- `qdrant` als eigener Dienst sichtbar machen, weil die Compose-Datei bereits existiert.
- Supabase vom Platzhalter in eine echte Compose-Integration ueberfuehren.
- Optional Element Web als Matrix-Client ergaenzen.
- Optional Admin-/Monitoring-Seiten fuer Dienste mit API-Status ergaenzen.
- Healthchecks aus Compose oder Dienstkatalog in der UI anzeigen.

## Priorisierte naechste Schritte

1. Zentralen Dienstkatalog einfuehren.
2. Doppelte Dienstdefinitionen entfernen.
3. Web-URLs aus Dienstkatalog und `.env` ableiten.
4. `ComposeWidget` entflechten und Podman-Runtime auslagern.
5. Auswahlmodell fuer Ausgabe und Auswahl-zuruecksetzen umsetzen.
6. Projekt- und Git-Hygiene fuer Laufzeitdaten verbessern.
7. Danach `matrix-synapse` im Dienstkatalog und in Compose ergaenzen.
8. Danach optional Element Web als Matrix-Client einbauen.

## Kritische Punkte

- Synapse darf nicht ohne persistente Konfiguration gestartet werden, weil sonst Serveridentitaet und Keys verloren gehen koennen.
- Matrix-Federation funktioniert nur mit sauberer Public-URL, TLS und Well-Known-Konfiguration.
- Secrets duerfen nicht in Git landen.
- Die Env-Verwaltung darf nicht wieder auf UI-Module verteilt werden.
- Neue Dienste sollten erst nach dem zentralen Dienstkatalog hinzugefuegt werden.
- Runtime-Datenverzeichnisse muessen konsequent ignoriert werden.
- Webnavigation darf nicht dauerhaft indexbasiert bleiben, wenn Dienste dynamisch hinzukommen.

## Zielbild

Nach Umsetzung der naechsten Ausbaustufe arbeitet die Anwendung so:

- Ein zentraler Dienstkatalog beschreibt Dienste, Container, Compose-Dateien, Env-Variablen, Webendpunkte und Auth-Modi.
- Die Verwaltungsseite zeigt Dienste, Containerstatus, Volumen und Ausgabe konsistent aus diesem Katalog.
- Podman-Laufzeitlogik liegt getrennt von der UI.
- Webseiten werden dynamisch aus effektiven Konfigurationswerten geladen.
- Optionaldienste wie Matrix/Synapse koennen ohne doppelte Pflege eingebunden werden.
- Der lokale private Betrieb und ein spaeterer oeffentlicher Betrieb sind in Compose und Konfiguration sauber getrennt.
