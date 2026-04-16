# Plan: Konsolen-Dialog in Status-Tabelle und Rest-Ausgabe aufteilen

## Ziel

`Schnittstelle/consolen_dialog.py` soll nicht mehr nur ein grosses Textfeld zeigen. Der Dialog soll laufende Podman-/Compose-/Ollama-Ausgaben in zwei Bereiche zerlegen:

- Oben eine Tabelle fuer strukturierbare Statusinformationen, vor allem Container, Images, Pulls, Downloads und abgeschlossene Schritte.
- Darunter ein Textfeld fuer alles, was nicht sauber tabellarisch darstellbar ist, zum Beispiel rohe Fehlermeldungen, Exit-Codes, Hinweise, Befehle, Warnungen und unerkannte Ausgabezeilen.

Die bestehende Prozesslogik soll erhalten bleiben:

- `PodmanProzessDialog` fuer einzelne Podman-Kommandos.
- `PodmanProzessKetteDialog` fuer mehrere aufeinanderfolgende Podman-Kommandos.
- `setze_abgeschlossen_callback(...)` liefert weiterhin die komplette Ausgabe als Text zurueck.
- Abbrechen, Zeitlimit, Close-Schutz und Schliessen bleiben fachlich unveraendert.

## Ist-Zustand

`Schnittstelle/consolen_dialog.py` enthaelt zwei sehr aehnliche Dialogklassen. Beide besitzen aktuell:

- `QLabel` fuer den Gesamtstatus.
- ein einzelnes `QPlainTextEdit` als komplette Prozessausgabe.
- Buttons fuer Abbrechen und Schliessen.
- `QProcess` mit `readyReadStandardOutput`, `readyReadStandardError`, `errorOccurred` und `finished`.
- eine interne Liste `_ausgabe`, die alle Textstuecke fuer den Abschluss-Callback sammelt.

Die Aufrufstellen sind:

- Compose-Stack starten in `Schnittstelle/verwaltung/compose_widget.py`.
- Compose-Stack neu starten in `Schnittstelle/verwaltung/compose_widget.py`.
- Compose-Stack stoppen in `Schnittstelle/verwaltung/compose_widget.py`.
- Ollama-Modell pull in `Schnittstelle/verwaltung/ollama_widget.py`.

## Zielbild UI

Der Dialog bekommt statt nur einem Textfeld diese Struktur:

1. Gesamtstatus oben wie bisher.
2. Status-Tabelle.
3. Rest-Ausgabe als schmaleres Textfeld darunter.
4. Aktionsbuttons wie bisher.

Vorgeschlagene Tabellen-Spalten:

- `Objekt`: Containername, Servicename, Image-Layer, Modellname oder sonstiger Zielname.
- `Typ`: `Container`, `Service`, `Image`, `Layer`, `Modell`, `Befehl`.
- `Zustand`: zum Beispiel `Pulling`, `Downloading`, `Starting`, `Started`, `Running`, `Done`, `Error`.
- `Fortschritt`: Prozent, Groesse oder leer.
- `Details`: kurze Zusatzinformation.

Falls die UI bewusst minimal bleiben soll, koennen die Spalten auf `Container` und `Zustand` reduziert werden. Technisch ist aber eine etwas breitere interne Struktur sinnvoll, weil Pull-/Download-Zeilen sonst in eine der beiden Spalten gequetscht werden.

## Architektur

### Gemeinsames Dialog-Basiswidget

Die Duplikation zwischen `PodmanProzessDialog` und `PodmanProzessKetteDialog` sollte reduziert werden, ohne die oeffentliche API stark umzubauen.

Plan:

1. Eine interne Hilfsklasse oder Basisklasse einfuehren, zum Beispiel `_PodmanAusgabeDialogBasis`.
2. Dort UI-Aufbau, Ausgabeverarbeitung, Tabelle, Rest-Textfeld und Parser halten.
3. `PodmanProzessDialog` und `PodmanProzessKetteDialog` behalten ihre Namen und Konstruktoren, delegieren aber gemeinsame Logik an die Basis.

Dadurch bleiben die Aufrufstellen weitgehend stabil.

### Datenmodell

Neue interne Dataclass:

```python
@dataclass
class ProzessStatusEintrag:
    schluessel: str
    objekt: str
    typ: str
    zustand: str
    fortschritt: str = ""
    details: str = ""
```

Der `schluessel` dient dazu, bestehende Tabellenzeilen zu aktualisieren statt bei jedem Fortschrittsupdate neue Zeilen anzulegen.

Beispiele:

- `container:n8n`
- `service:neo4j`
- `image-layer:sha256:...`
- `ollama-model:llama3.2`

### Parser

Neue interne Klasse, zum Beispiel `PodmanAusgabeParser`.

Aufgabe:

- Textchunks aus stdout/stderr annehmen.
- `\r`-basierte Fortschrittsausgaben normalisieren.
- erkannte Statuszeilen als `ProzessStatusEintrag` liefern.
- unerkannte Zeilen als Rest-Ausgabe zurueckgeben.

Wichtig: Der Parser darf keine Ausgabe verlieren. Jede nicht eindeutig erkannte Zeile muss ins untere Textfeld.

## Erkennungsregeln

### 1. Podman Compose Fortschritt

Typische Compose-Ausgaben koennen enthalten:

- Container erstellt, gestartet, gestoppt oder entfernt.
- Services oder Images werden gepullt.
- Layer werden heruntergeladen oder entpackt.
- Schritte werden mit Haken, Spinnern oder Statuswoertern ausgegeben.

Der Parser sollte schrittweise arbeiten:

1. ANSI-Steuerzeichen entfernen.
2. Sonderzeichen fuer Fortschritt tolerieren.
3. Bekannte Statuswoerter suchen:
   - `Pulling`
   - `Pulled`
   - `Downloading`
   - `Extracting`
   - `Creating`
   - `Created`
   - `Starting`
   - `Started`
   - `Stopping`
   - `Stopped`
   - `Removing`
   - `Removed`
   - `Error`
   - `Done`
4. Wenn eine Zeile ein Objekt plus Status enthaelt, Tabellenzeile aktualisieren.
5. Wenn keine sichere Zuordnung moeglich ist, Zeile in die Rest-Ausgabe schreiben.

### 2. Ollama Pull

Ollama-Pull-Ausgaben sollen ebenfalls in die Tabelle, soweit moeglich:

- `pulling manifest`
- `pulling <digest> ...`
- `verifying sha256 digest`
- `writing manifest`
- `success`
- Prozent- oder Groessenfortschritt bei Layern

Vorgeschlagene Zuordnung:

- Modellname aus dem aufgerufenen Kommando als Tabellenobjekt, wenn die Ausgabe keinen eigenen Namen enthaelt.
- Digest-/Layer-Zeilen als `Layer`.
- Abschlusszeilen als `Modell` mit Zustand `Done`.

### 3. Fehler und Hinweise

Fehler sollen zweigleisig behandelt werden:

- Wenn eine Zeile ein konkretes Objekt enthaelt, Tabelle mit Zustand `Error` aktualisieren.
- Die vollstaendige Fehlermeldung bleibt zusaetzlich im unteren Textfeld, damit keine Diagnoseinformation verloren geht.

Exit-Codes, Timeout-Hinweise, Abbruchmeldungen und `QProcess`-Fehler bleiben im Textfeld.

## UI-Verhalten

- Die Tabelle aktualisiert bestehende Zeilen live.
- Neue Objekte werden unten angefuegt.
- Die Tabelle scrollt optional zum zuletzt geaenderten Eintrag.
- Das Textfeld bleibt read-only und scrollt wie bisher ans Ende.
- Bei sehr vielen Download-Layern sollte die Tabelle nicht unendlich wachsen; fuer Layer kann spaeter eine Begrenzung oder Zusammenfassung eingebaut werden.
- Die komplette Roh-Ausgabe bleibt weiterhin in `_ausgabe`, damit bestehende Callback-Nutzer keine Verhaltensaenderung bekommen.

## Umsetzungsschritte

1. In `Schnittstelle/consolen_dialog.py` die benoetigten Widgets importieren:
   - `QTableWidget`
   - `QTableWidgetItem`
   - `QHeaderView`
   - optional `QSplitter`
2. `ProzessStatusEintrag` und `PodmanAusgabeParser` einfuehren.
3. Eine gemeinsame Methode fuer UI-Aufbau einfuehren:
   - Statuslabel
   - Tabelle
   - Rest-Ausgabefeld
   - Buttons
4. `_haenge_ausgabe_an(...)` umbauen:
   - Rohtext weiter in `_ausgabe` sammeln.
   - Parser mit neuem Textchunk fuettern.
   - erkannte Eintraege in Tabelle upserten.
   - Resttext ins Textfeld schreiben.
5. Gemeinsame Tabellenlogik bauen:
   - `_setze_status_eintrag(eintrag)`
   - `_zeile_fuer_schluessel`
   - `_aktualisiere_status_zeile`
6. `PodmanProzessDialog` auf die neue Ausgabe-UI umstellen.
7. `PodmanProzessKetteDialog` auf dieselbe Ausgabe-UI umstellen.
8. Befehlskopfzeilen wie `$ podman ...` und `## Schritt ...` bewusst als Rest-Ausgabe anzeigen.
9. Prozessfehler, Timeout und Abbruchmeldungen weiter im Resttext anzeigen.
10. Abschlussstatus optional in Tabelle aufnehmen:
    - Bei Erfolg eine Zeile `Befehl | Done`.
    - Bei Fehler eine Zeile `Befehl | Error`.

## Testplan

### Manuelle Tests

1. Compose-Stack starten.
   - Containerstatus erscheint in der Tabelle.
   - sonstige Compose-Ausgabe bleibt unten.
2. Compose-Stack stoppen.
   - Stop-/Remove-Status erscheint in der Tabelle.
3. Compose-Stack neu starten.
   - Beide Kommandos der Kette werden sauber getrennt.
   - Tabelle bleibt ueber beide Schritte erhalten oder markiert den aktuellen Schritt eindeutig.
4. Ollama-Modell pull aus dem Ollama-Widget.
   - Modell-/Layer-/Downloadfortschritt erscheint in der Tabelle.
   - Rohhinweise und Fehler bleiben unten sichtbar.
5. Fehlerfall: nicht existierender Container oder falscher Modellname.
   - Tabelle zeigt Fehler, falls ein Objekt erkannt wurde.
   - Voller Fehlertext steht unten.
6. Abbrechen waehrend laufendem Prozess.
   - Abbruchmeldung steht unten.
   - Dialog laesst sich erst nach Prozessende schliessen.

### Automatisierbare Tests

Falls Tests fuer Qt-lose Logik gewuenscht sind:

1. Parser in eine eigene, GUI-unabhaengige Klasse legen.
2. Unit-Tests fuer Beispielzeilen schreiben:
   - Compose Container Started
   - Compose Pulling/Downloading
   - Ollama pulling manifest
   - Ollama Layer mit Prozent
   - unerkannte Zeile
   - Fehlerzeile
3. Sicherstellen, dass unerkannte Zeilen nie verloren gehen.

## Risiken

- Podman-/Compose-Ausgaben unterscheiden sich je nach Version, Terminalmodus und Sprache.
- Fortschrittsausgaben nutzen oft `\r`; ohne richtige Normalisierung entstehen sehr viele Zwischenzeilen.
- Unicode-Symbole aus Compose-Ausgaben koennen je nach Umgebung fehlen oder anders aussehen.
- Zu aggressive Parserregeln koennen Diagnosezeilen faelschlich aus dem Textfeld entfernen.
- Eine rein zweispaltige Tabelle ist fuer Downloads und Layer-Fortschritt wahrscheinlich zu eng.

## Geklaerte Entscheidungen

1. Die Tabelle bekommt zusaetzliche Spalten. Geplant sind `Objekt`, `Typ`, `Zustand`, `Fortschritt` und `Details`.
2. Downloads und Pulls werden zu einer Zeile pro Dienst beziehungsweise pro Modell zusammengefasst. Es soll keine eigene Tabellenzeile pro Image-Layer geben.
3. Das untere Textfeld zeigt nur Ausgabe, die nicht sinnvoll ueber die Tabelle dargestellt werden kann.
4. Die Tabelle bleibt nach Prozessende erhalten. Der `Schliessen`-Button bleibt wie bisher erst aktiv, wenn der Prozess fertig ist.
5. Fehler, die in der Tabelle als `Error` erkannt werden, stehen zusaetzlich immer im unteren Textfeld, damit Diagnoseinformationen erhalten bleiben.

## Offene Fragen

Aktuell keine offenen fachlichen Fragen.

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

Geklaerte Zielrichtung:

- Der Matrix-Server soll primaer privat ueber Tailscale erreichbar sein, aehnlich wie Immich.
- Eine eigene gekaufte Domain ist fuer diesen privaten Betrieb nicht notwendig.
- Der vorhandene Tailscale-Geraetename des Rechners `teutonrechner` soll nicht geaendert werden.
- Matrix soll deshalb einen eigenen Tailscale-Containerdienst mit eigenem Tailnet-Hostname bekommen.
- Als stabiler Matrix-Servername soll der vollstaendige Tailscale-Name dieses Containers verwendet werden, zum Beispiel `selatrix.huchen-pirate.ts.net`.
- Der reine Kurzname `selatrix` sollte nicht als `server_name` verwendet werden, weil Matrix-IDs und Client-Autodiscovery mit einem stabilen vollstaendigen Namen robuster sind.
- Eine gekaufte Domain wird erst relevant, wenn spaeter oeffentliche Federation, ein schoenerer Matrix-Name wie `@user:selatrix.de` oder Zugriff ohne Tailscale gewuenscht ist.
- Element Web soll mit eingeplant werden, damit Matrix direkt in der Anwendung nutzbar ist.
- Registrierung soll Invite-only beziehungsweise admin-kontrolliert sein.
- Der Server soll fuer Kommunikation mit n8n nutzbar sein. Dafuer wird ein eigener Matrix-Bot/API-Nutzer fuer n8n eingeplant.
- Direkte Nutzer-zu-Nutzer-Kommunikation soll innerhalb des privaten Servers moeglich sein.
- VoIP, Anrufe und Sprachnachrichten sind aktuell nicht Ziel der Umsetzung. TURN/coturn wird deshalb nicht initial installiert.
- E-Mail/SMTP wird initial nicht eingerichtet.
- Persistenz soll ueber eigene Podman-Volumes laufen, nicht ueber Bind-Mounts in den Projektbaum.

Ziel:

- Der Stack soll um einen privaten Matrix-Homeserver auf Basis von Synapse erweitert werden.
- Die Integration soll dieselben Mechanismen nutzen wie die vorhandenen Dienste:
  - zentraler Dienstkatalog
  - Compose-Override
  - Env-Verwaltung
  - Containerstatus
  - Logausgabe
  - eingebettete Weboberflaeche ueber Element Web
  - eigene Podman-Volumes fuer persistente Daten
  - eigener Tailscale-Container mit eigener Tailnet-Identitaet
  - klare Trennung zwischen privatem Tailscale-Betrieb und spaeterem Public/Federation-Betrieb

Geplante Dienststruktur:

- Dienst-ID fuer Synapse: `matrix-synapse`
- Anzeigename: `Matrix Synapse`
- Hauptcontainer: `matrix-synapse`
- Datenbankcontainer: `matrix-postgres`
- Tailscale-Container: `matrix-tailscale`
- interner Reverse-Proxy: `matrix-proxy`
- Webclient-Dienst-ID: `matrix-element`
- Webclient-Anzeigename: `Element Web`
- Interne Synapse-Ports:
  - Client-Server API: `8008`
  - Federation-Port `8448` wird initial nicht veroeffentlicht
- Lokale private Veroeffentlichung:
  - Synapse lokal: `127.0.0.1:${MATRIX_SYNAPSE_PRIVATE_PORT:-8010}:8008`
  - Element lokal: `127.0.0.1:${MATRIX_ELEMENT_PRIVATE_PORT:-8011}:80`
- Tailscale-Zugriff:
  - eigener Tailnet-Hostname ueber `TS_HOSTNAME=selatrix`
  - eigener Tailscale-State im Podman-Volume `matrix_tailscale_state`
  - Zugriff ueber `https://selatrix.huchen-pirate.ts.net`
  - Synapse-Client-API unter `https://selatrix.huchen-pirate.ts.net/_matrix`
  - Element Web unter `https://selatrix.huchen-pirate.ts.net/`
- Oeffentliche Federation:
  - wird nicht initial umgesetzt
  - bleibt als spaeteres Public-Overlay moeglich

Neue Compose-Dateien:

1. `Kern/compose/compose.override.matrix-postgres.yml`
   - eigener Postgres-Dienst fuer Synapse
   - eigener Podman-Volume `matrix_postgres_data`
   - Healthcheck mit `pg_isready`
   - Datenbank muss UTF-8-kompatibel angelegt werden
   - Variablen:
     - `MATRIX_POSTGRES_DB`
     - `MATRIX_POSTGRES_USER`
     - `MATRIX_POSTGRES_PASSWORD`
     - `MATRIX_POSTGRES_VERSION`
2. `Kern/compose/compose.override.matrix-synapse.yml`
   - Synapse-Container mit offiziellem Image `matrixdotorg/synapse`
   - eigener Podman-Volume `matrix_synapse_data` fuer `/data`
   - Abhaengigkeit von `matrix-postgres`
   - Healthcheck gegen `http://localhost:8008/health`
   - keine automatische Ueberschreibung von `/data/homeserver.yaml`
   - Variablen:
     - `MATRIX_SERVER_NAME`
     - `MATRIX_PUBLIC_BASEURL`
     - `MATRIX_SYNAPSE_REPORT_STATS`
     - `MATRIX_REGISTRATION_SHARED_SECRET`
     - `MATRIX_MACAROON_SECRET_KEY`
     - `MATRIX_FORM_SECRET`
     - `MATRIX_SYNAPSE_PRIVATE_PORT`
3. `Kern/compose/compose.override.matrix-element.yml`
   - Element-Web-Container
   - eigener statischer Element-Konfigurations-Mount oder generierte Konfiguration
   - Homeserver-URL zeigt auf `MATRIX_PUBLIC_BASEURL`
   - lokaler Port ueber `MATRIX_ELEMENT_PRIVATE_PORT`
4. `Kern/compose/compose.override.matrix-tailscale.yml`
   - Tailscale-Container mit offiziellem Image `tailscale/tailscale`
   - eigener Podman-Volume `matrix_tailscale_state` fuer `/var/lib/tailscale`
   - `TS_HOSTNAME=selatrix`
   - `TS_STATE_DIR=/var/lib/tailscale`
   - `TS_AUTH_ONCE=true`
   - initiale Anmeldung ueber `TAILSCALE_AUTHKEY`
   - Auth-Key liegt vor, wird aber nicht in `plan.md` dokumentiert
   - Serve-/Proxy-Konfiguration fuer privaten Tailnet-Zugriff
5. `Kern/compose/compose.override.matrix-proxy.yml`
   - interner Reverse-Proxy fuer Matrix-Pfade
   - `/` leitet auf `matrix-element`
   - `/_matrix` leitet auf `matrix-synapse:8008`
   - `/_synapse/client` leitet auf `matrix-synapse:8008`
   - keine oeffentliche Portfreigabe; Zugriff erfolgt ueber `matrix-tailscale`

Initialisierung:

1. Einen vorbereitenden Schritt fuer Synapse-Konfiguration definieren.
2. Beim ersten Start muss `/data/homeserver.yaml` erzeugt werden.
3. Die Generierung darf nur laufen, wenn noch keine `homeserver.yaml` existiert.
4. Die generierte Konfiguration muss danach fuer Postgres, `public_baseurl`, Invite-only/Registration, deaktivierte E-Mail und Secrets angepasst werden.
5. Signing-Key, Medien, Uploads und Konfiguration bleiben im Podman-Volume `matrix_synapse_data`.
6. Der initiale Admin-Nutzer wird nach dem ersten erfolgreichen Start per `register_new_matrix_user` erzeugt.
7. Geplanter Admin-Anzeigename: `Alexander`.
8. Danach wird ein eigener n8n-Bot-Nutzer erzeugt, dessen Access Token in `.env` oder in einer spaeteren Secret-Verwaltung abgelegt wird.
9. Geplanter n8n-Bot-Localpart: `selatrix`; geplanter Anzeigename: `selatrix (chat)`.

Invite-only und Nutzer:

1. Offene Registrierung bleibt deaktiviert.
2. Neue Nutzer werden durch Admin-Aktion oder eine kontrollierte Invite-/Registrierungslogik angelegt.
3. Fuer n8n wird ein eigener Nutzer eingeplant, zum Beispiel `@selatrix:selatrix.huchen-pirate.ts.net` mit Anzeigename `selatrix (chat)`.
4. n8n kann ueber die Matrix Client-Server API Nachrichten senden und Raeume/Direct Messages nutzen.
5. Direkte Kommunikation zwischen menschlichen Nutzern laeuft ueber Element Web oder mobile Matrix-Clients, solange diese den Tailscale-Namen erreichen.

Dienstkatalog-Erweiterung:

1. `matrix-synapse` in den zentralen Dienstkatalog aufnehmen.
2. `matrix-element` in den zentralen Dienstkatalog aufnehmen.
3. `matrix-tailscale` und `matrix-proxy` als technische Begleitdienste aufnehmen oder den Matrix-Diensten intern zuordnen.
4. Compose-Dateien zuordnen:
   - `compose.override.matrix-postgres.yml`
   - `compose.override.matrix-synapse.yml`
   - `compose.override.matrix-element.yml`
   - `compose.override.matrix-tailscale.yml`
   - `compose.override.matrix-proxy.yml`
5. Container-Aliase zuordnen:
   - `matrix-synapse`
   - `synapse`
   - `matrix-postgres`
   - `matrix-element`
   - `element`
   - `matrix-tailscale`
   - `matrix-proxy`
6. Webeintrag fuer Element Web definieren:
   - Titel: `Element`
   - URL aus `MATRIX_ELEMENT_HOSTNAME` oder lokal `http://localhost:8011`
   - Auth-Modus: `formular/manuell`
7. Synapse selbst bleibt primaer API-Dienst. Eine eigene Detailseite kann spaeter Status, Servername und Federation-Hinweise anzeigen.

Env-Verwaltung:

1. Pflichtvariablen fuer Matrix/Synapse:
   - `MATRIX_SERVER_NAME`
   - `MATRIX_PUBLIC_BASEURL`
   - `MATRIX_POSTGRES_PASSWORD`
   - `MATRIX_REGISTRATION_SHARED_SECRET`
   - `MATRIX_MACAROON_SECRET_KEY`
   - `MATRIX_FORM_SECRET`
   - `TAILSCALE_AUTHKEY`
2. Standardwerte nur fuer ungefaehrliche lokale Werte setzen:
   - `MATRIX_POSTGRES_DB=synapse`
   - `MATRIX_POSTGRES_USER=synapse`
   - `MATRIX_POSTGRES_VERSION=16`
   - `MATRIX_SYNAPSE_REPORT_STATS=no`
   - `MATRIX_SYNAPSE_PRIVATE_PORT=8010`
   - `MATRIX_ELEMENT_PRIVATE_PORT=8011`
   - `TAILSCALE_HOSTNAME=selatrix`
3. Secrets muessen vom Nutzer gesetzt oder durch eine sichere Generatorfunktion erzeugt werden.
4. `.compose.state.json` darf langfristig keine Secrets im Klartext persistieren. Vor Matrix sollte die Persistenz der effektiven Umgebungsvariablen ueberarbeitet werden.
5. Der Einstellungen-Dialog muss die Variablen anzeigen, sobald Matrix ausgewaehlt ist.

UI-Integration:

1. Matrix/Synapse als optionalen Dienst in der Verwaltung anzeigen.
2. Element Web als optionalen oder automatisch mit Matrix aktivierten Dienst anzeigen.
3. Status fuer Synapse, Matrix-Postgres, Element, Matrix-Proxy und Tailscale aus Container-Aliasen erkennen.
4. Logs fuer Synapse und Element anzeigen.
5. Webnavigation fuer Element Web aktivieren.
6. Optional spaeter eigene Matrix-Detailseite bauen:
   - Servername
   - Public Base URL
   - Tailscale-Hinweis
   - Registrierungsstatus
   - n8n-Bot-Status
   - Federation-Hinweis

Tailscale- und Domain-Planung:

1. Fuer den geplanten privaten Betrieb wird keine gekaufte Domain benoetigt.
2. Voraussetzung ist, dass alle Clients, inklusive Handy und ggf. n8n-Host, im selben Tailnet sind oder den Tailscale-Endpunkt erreichen.
3. Der Matrix-Servername sollte vor dem ersten Start final feststehen, weil er in Matrix-IDs und Signaturen eingeht.
4. Empfohlener Wert:
   - `MATRIX_SERVER_NAME=selatrix.huchen-pirate.ts.net`
   - `MATRIX_PUBLIC_BASEURL=https://selatrix.huchen-pirate.ts.net`
5. Der Rechner darf im Tailnet weiter `teutonrechner` heissen; der Matrix-Tailscale-Container bekommt separat den Hostnamen `selatrix`.
6. Tailscale-Konfiguration:
   - `TAILSCALE_HOSTNAME=selatrix`
   - `TAILSCALE_AUTHKEY` liegt vor und wird nur in `.env` oder einer spaeteren Secret-Verwaltung abgelegt.
   - Fuer die Umsetzung sollte ein frischer Einmal-Auth-Key verwendet werden, weil der aktuelle Key im Chatverlauf steht.
   - `matrix_tailscale_state` muss persistent bleiben, damit der Container nicht bei jedem Neustart als neues Geraet erscheint.
   - `TS_AUTH_ONCE=true` verhindert unnoetige Neuanmeldungen, sobald State vorhanden ist.
7. Synapse und Element laufen unter demselben Tailscale-Namen:
   - Element Web: `https://selatrix.huchen-pirate.ts.net/`
   - Synapse Client-API: `https://selatrix.huchen-pirate.ts.net/_matrix`
   - Synapse Zusatzpfad: `https://selatrix.huchen-pirate.ts.net/_synapse/client`
8. Wenn spaeter Federation mit fremden Matrix-Servern gewuenscht ist, muss die Architektur neu bewertet werden:
   - eigene Domain oder stabiler oeffentlicher DNS-Name
   - TLS
   - Reverse Proxy
   - `.well-known/matrix/client`
   - `.well-known/matrix/server`
   - Federation-Port oder Delegation
9. Tailscale Funnel waere eine moegliche spaetere Public-Option, macht den Dienst aber oeffentlich und passt nicht zum aktuellen privaten Ziel.

Backup-Strategie:

1. Fuer Synapse-Daten wird das Podman-Volume `matrix_synapse_data` gesichert.
2. Fuer Postgres wird bevorzugt ein konsistenter Dump erzeugt, statt das laufende Datenvolume roh zu kopieren.
3. Geplante Backup-Artefakte:
   - `synapse-YYYYMMDD-HHMM.sql` aus `pg_dump`
   - `matrix-synapse-data-YYYYMMDD-HHMM.tar` aus `podman volume export matrix_synapse_data`
4. Das Postgres-Datenvolume `matrix_postgres_data` bleibt persistent, wird aber nicht als primaere Backup-Methode im laufenden Betrieb kopiert.
5. Spaeter kann die App dafuer einen Backup-Button bekommen.

Nicht initial umsetzen:

- Keine Federation mit fremden Matrix-Servern.
- Kein TURN/coturn.
- Keine VoIP-/Anruf-Funktionen.
- Keine offene Registrierung.
- Keine E-Mail-/SMTP-Funktion.
- Keine harte Public-Caddy-Konfiguration, solange der Betrieb privat ueber Tailscale geplant ist.

Vor Implementierung noch konkret festlegen:

1. Tailnet-Suffix ist festgelegt: `huchen-pirate.ts.net`.
2. Matrix-FQDN ist festgelegt: `selatrix.huchen-pirate.ts.net`.
3. Tailscale-Auth-Key fuer den Containerdienst `selatrix` liegt vor und wird nicht in die Planungsdatei geschrieben.
4. Synapse und Element laufen unter demselben Tailscale-Namen mit Pfad-Routing.
5. Name des ersten Admin-Nutzers: `Alexander`.
6. Name des n8n-Bot-Nutzers: Localpart `selatrix`, Anzeigename `selatrix (chat)`.
7. Backup-Strategie: Postgres per `pg_dump`, Synapse-Daten per Volume-Export.

Abnahmekriterien:

- `matrix-synapse` kann als optionaler Dienst ausgewaehlt werden.
- `matrix-element` kann gestartet und in der App geoeffnet werden.
- Die notwendigen Env-Variablen erscheinen im Einstellungen-Dialog.
- `podman compose` startet Synapse mit eigenem Postgres.
- Synapse-Daten, Konfiguration, Medien und Signing-Key bleiben in eigenen Podman-Volumes persistent.
- Der Matrix-Tailscale-Container erscheint im Tailnet als eigener Host `selatrix`, ohne den Rechnernamen `teutonrechner` zu aendern.
- Element Web ist unter `https://selatrix.huchen-pirate.ts.net/` erreichbar.
- Synapse ist unter `https://selatrix.huchen-pirate.ts.net/_matrix` erreichbar.
- Offene Registrierung ist deaktiviert.
- Initialer Admin-Nutzer und n8n-Bot-Nutzer koennen angelegt werden.
- n8n kann ueber den Bot-Nutzer Matrix-Nachrichten senden.
- Private Nutzung funktioniert ueber Tailscale ohne gekaufte Domain.
- VoIP, TURN, SMTP/E-Mail und Public Federation bleiben bewusst deaktiviert.

### Weitere geplante Dienste und Ausbauten

- `qdrant` als eigener Dienst sichtbar machen, weil die Compose-Datei bereits existiert.
- Supabase vom Platzhalter in eine echte Compose-Integration ueberfuehren.
- Element Web zusammen mit Matrix als eingebetteten Client ergaenzen.
- Optional Admin-/Monitoring-Seiten fuer Dienste mit API-Status ergaenzen.
- Healthchecks aus Compose oder Dienstkatalog in der UI anzeigen.

## Priorisierte naechste Schritte

1. Zentralen Dienstkatalog einfuehren.
2. Doppelte Dienstdefinitionen entfernen.
3. Web-URLs aus Dienstkatalog und `.env` ableiten.
4. `ComposeWidget` entflechten und Podman-Runtime auslagern.
5. Auswahlmodell fuer Ausgabe und Auswahl-zuruecksetzen umsetzen.
6. Projekt- und Git-Hygiene fuer Laufzeitdaten verbessern.
7. Danach `matrix-synapse` und `matrix-element` im Dienstkatalog und in Compose ergaenzen.
8. Danach Matrix-Initialisierung, Admin-Nutzer und n8n-Bot-Nutzer automatisieren oder dokumentiert in der UI fuehren.

## Kritische Punkte

- Synapse darf nicht ohne persistente Konfiguration gestartet werden, weil sonst Serveridentitaet und Keys verloren gehen koennen.
- Matrix-Federation funktioniert nur mit sauberer Public-URL, TLS und Well-Known-Konfiguration; sie ist fuer den Tailscale-Privatbetrieb nicht initial vorgesehen.
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
