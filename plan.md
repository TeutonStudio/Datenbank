**Analyse**
- Der Ordner heißt im Projekt aktuell `legacy`, nicht `Legacy`. Die neue UI ist noch ein Gerüst: statische Sidebar mit zwei Einträgen und leerem `QStackedWidget` in [ui/haupt_fenster.py](/home/alex/Programme/Container/N8nAnwendung/ui/haupt_fenster.py#L29), dazu ist die Containerauswahl nur als TODO angelegt in [ui/verwaltung/container.py](/home/alex/Programme/Container/N8nAnwendung/ui/verwaltung/container.py#L1).
- Die aktuelle Sidebar arbeitet nur mit Textlisten; für dynamische Addon-Einträge reicht das nicht. Außerdem ist der Icon-Pfad aktuell falsch aufgebaut in [ui/vertikale_leiste.py](/home/alex/Programme/Container/N8nAnwendung/ui/vertikale_leiste.py#L48).
- Die Legacy-Startlogik ist stark auf Docker fest verdrahtet: `docker compose`, `docker ps`, `docker exec`, `docker inspect`, `docker rm` in [legacy/start_services.py](/home/alex/Programme/Container/N8nAnwendung/legacy/start_services.py#L54) und [legacy/LocalAI.py](/home/alex/Programme/Container/N8nAnwendung/legacy/LocalAI.py#L116).
- Für die Neuentwicklung sind aus `legacy/LocalAI.py` aber mehrere Bausteine wiederverwendbar: Compose-Erkennung und Service-Parsing [legacy/LocalAI.py](/home/alex/Programme/Container/N8nAnwendung/legacy/LocalAI.py#L116), eingebetteter Browser mit Login-Handling [legacy/LocalAI.py](/home/alex/Programme/Container/N8nAnwendung/legacy/LocalAI.py#L304), UI-URL-Ableitung [legacy/LocalAI.py](/home/alex/Programme/Container/N8nAnwendung/legacy/LocalAI.py#L727), Status-/Port-Polling [legacy/LocalAI.py](/home/alex/Programme/Container/N8nAnwendung/legacy/LocalAI.py#L955).
- Aus den privaten Port-Freigaben ergeben sich als klare Web-Kandidaten: `n8n`, `flowise`, `open-webui`, `neo4j`, `langfuse-web`, `minio`-Console, `searxng`; `graphiti` ist eher API/SSE als echte Weboberfläche [legacy/docker-compose.override.private.yml](/home/alex/Programme/Container/N8nAnwendung/legacy/docker-compose.override.private.yml#L1), [legacy/docker-compose.override.graphiti.yml](/home/alex/Programme/Container/N8nAnwendung/legacy/docker-compose.override.graphiti.yml#L24).
- Supabase ist ein Sonderfall: die Legacy-Logik klont die Compose-Dateien erst zur Laufzeit [legacy/start_services.py](/home/alex/Programme/Container/N8nAnwendung/legacy/start_services.py#L25). Im aktuellen Repo existiert `supabase/` nicht.

**Umsetzungsplan**
1. Eine Runtime-Abstraktion einführen, z.B. `ContainerRuntime`, damit die neue Verwaltung nirgends mehr direkt `docker ...` aufruft, sondern nur noch `runtime.compose_up`, `compose_down`, `compose_ps`, `logs`, `inspect`, `remove`. Primärziel ist Podman; Docker bleibt höchstens als Fallback.
2. Eine Start-/Voraussetzungsprüfung bauen, die `podman`, den Compose-Frontend-Befehl, `git` und ggf. `openssl` prüft. Bei fehlendem Podman soll die Verwaltung nicht abstürzen, sondern den Status `nicht installiert` zeigen und Installationshinweise ausgeben statt blind zu installieren.
3. Einen zentralen Service-Katalog definieren statt URLs aus Tabellenzellen abzuleiten. Pro Dienst: `id`, Anzeigename, Kategorie (`core`/`addon`), Podman-Compose-Service-Name, Standard-Auswahl, Web-URL-Regel, Auth-Hinweis, Profilbindung (`cpu/gpu`), optionales Icon.
4. Die Containerauswahl in [ui/verwaltung/container.py](/home/alex/Programme/Container/N8nAnwendung/ui/verwaltung/container.py#L1) als echte Verwaltungsseite umsetzen: Liste/Tabelle mit Checkbox, Statussymbolen (`aktiv`, `inaktiv`, `nicht installiert`), plus Aktionen `Start`, `Stop`, `Neustart`, `Löschen`.
5. Die Auswahl persistent speichern, z.B. in einer JSON-Datei unterhalb des Projekts. Diese Auswahl steuert sowohl die Compose-Starts als auch die dynamischen Sidebar-Einträge.
6. Die Sidebar von einer simplen `list[str]` auf strukturierte Navigation umbauen: feste Einträge wie `Verwaltung` plus dynamisch erzeugte Addon-Einträge. Jedes Sidebar-Item braucht mindestens `id`, `label`, `icon`, `page_factory`.
7. Das zentrale `QStackedWidget` in [ui/haupt_fenster.py](/home/alex/Programme/Container/N8nAnwendung/ui/haupt_fenster.py#L60) nicht mehr jedes Mal neu aufbauen, sondern Seiten cachen. Für jeden Web-Zusatz wird genau ein `QWebEngineView` erzeugt und danach nur noch ein-/ausgeblendet.
8. Damit Logins beim Umschalten erhalten bleiben, die Web-Seiten persistent halten: pro Addon eine feste `QWebEngineView`-Instanz, optional alle mit gemeinsamem `QWebEngineProfile`. Solange die Widgets nicht zerstört werden, bleibt die Session im laufenden Programm erhalten.
9. Die dynamischen Sidebar-Einträge aus zwei Signalen ableiten: `ausgewählt` und `webfähig`. Optional zusätzlich `laufend/erreichbar`, falls du Einträge nur bei tatsächlich laufender UI sehen willst.
10. Die Legacy-Statuslogik übernehmen, aber an die neue Runtime koppeln: Compose-Konfiguration lesen, laufende Container per `ps` abgleichen, Ports auflösen, HTTP-Erreichbarkeit mit Hysterese prüfen. Das ist die Grundlage für Statusfarben, Aktiv-Symbole und die Entscheidung, ob ein Web-Eintrag klickbar ist.
11. Die Legacy-Startsequenz funktional migrieren: Supabase-Vorbereitung, `.env`-Sync, SearXNG-First-Run-Anpassung und optional Graphiti bleiben eigene Orchestrierungsschritte, aber nicht mehr in einem Docker-spezifischen Skript.
12. `einstieg.py` sollte die Python-Paketprüfung von der Containerprüfung trennen. PyQt kann weiter geprüft werden, Podman aber nur melden oder per expliziter Benutzeraktion installieren lassen.

**Rückfragen**
- Soll ein Web-Addon in der Sidebar erscheinen, sobald es ausgewählt ist, oder erst wenn der Container wirklich läuft?
- Welche Dienste sollen initial als Web-Zusätze gelten: nur `n8n`, `Open WebUI`, `Flowise`, `Langfuse`, `Neo4j`, `MinIO`, `SearXNG`, `Supabase Studio`?
- Soll `Supabase` weiterhin Teil des Systems sein, obwohl die Compose-Dateien aktuell erst per Git-Clone geholt werden?
- Wenn `Supabase` bleiben soll: lieber weiter zur Laufzeit klonen oder die benötigten Compose-Dateien direkt ins Projekt übernehmen?
- Soll ausschließlich `podman` unterstützt werden, oder soll die Runtime zusätzlich `podman compose` und `podman-compose` automatisch erkennen?
- Möchtest du bei fehlendem Podman nur einen Hinweis anzeigen oder aus der UI heraus eine Installation anstoßen?
- Welche Zielplattformen willst du unterstützen: nur Linux/Fedora, oder auch andere Distributionen?
- Soll die Login-Session nur beim Umschalten innerhalb einer App-Sitzung erhalten bleiben, oder auch nach einem kompletten Neustart der Anwendung?
- Welche Container sind Pflichtbestandteil des Stacks und dürfen nicht abwählbar sein?
- Sollen CPU/GPU-Profile für Ollama aus der Legacy-Version erhalten bleiben?
- Soll `Graphiti` überhaupt im neuen Verwalter auftauchen, obwohl es eher eine API als eine Benutzeroberfläche ist?
- Wie soll die Containerauswahl fachlich arbeiten: Auswahl einzelner Dienste oder Auswahl vordefinierter Pakete/Presets?

Wenn du die Rückfragen beantwortest, kann ich daraus direkt einen umsetzbaren Architekturplan mit Modulzuschnitt und Datenmodell für den neuen Verwalter ableiten.