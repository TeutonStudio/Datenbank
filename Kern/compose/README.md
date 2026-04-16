# Compose layout

Die Dateien in diesem Ordner sind für `podman compose` als zusammensetzbare Teilstücke gedacht.
Alle Bind-Mount-Pfade sind relativ zu [compose.yml](/home/alex/Programme/Container/Selatrix/Kern/compose/compose.yml) und zeigen deshalb mit `../` ins Projektwurzelverzeichnis.

## Typische Nutzung

Für ein lokales Setup mit n8n, seiner Datenbank und Open WebUI:

```sh
podman compose \
  -f compose/compose.yml \
  -f compose/compose.override.n8n-db.yml \
  -f compose/compose.override.n8n.yml \
  -f compose/compose.override.open-webui.yml \
  -f compose/compose.override.private.yml \
  up -d
```

Für Langfuse müssen zusätzlich seine Infrastrukturdateien geladen werden:

```sh
podman compose \
  -f compose/compose.yml \
  -f compose/compose.override.langfuse-postgres.yml \
  -f compose/compose.override.clickhouse.yml \
  -f compose/compose.override.redis.yml \
  -f compose/compose.override.minio.yml \
  -f compose/compose.override.langfuse.yml \
  -f compose/compose.override.private.yml \
  up -d
```

Für Ollama wird genau ein Profil gewählt:

```sh
podman compose \
  --profile cpu \
  -f compose/compose.yml \
  -f compose/compose.override.ollama.yml \
  -f compose/compose.override.private.yml \
  up -d
```

Für Immich werden Server, Machine Learning, Redis/Valkey und Postgres zusammen geladen:

```sh
podman compose \
  -f compose/compose.yml \
  -f compose/compose.override.immich.yml \
  -f compose/compose.override.private.yml \
  up -d
```

Für Matrix/Synapse werden Synapse, eigener Postgres, Element Web und ein interner
Caddy-Proxy geladen:

```sh
podman compose \
  -f compose/compose.yml \
  -f compose/compose.override.matrix-postgres.yml \
  -f compose/compose.override.matrix-synapse.yml \
  -f compose/compose.override.matrix-element.yml \
  -f compose/compose.override.matrix-proxy.yml \
  up -d
```

Element Web lauscht im Container auf `MATRIX_ELEMENT_INTERNAL_PORT` mit Standard
`8080`, weil das Image unprivilegiert laeuft und unter Podman nicht verlaesslich
auf Port `80` binden kann.

Tailscale ist ein eigener Dienst und kann separat oder zusammen mit Matrix
geladen werden:

```sh
podman compose \
  -f compose/compose.yml \
  -f compose/compose.override.tailscale.yml \
  up -d
```

Wenn Tailscale Matrix veroeffentlichen soll, muessen Matrix und Tailscale
gleichzeitig laufen. Der Tailscale-Serve-Endpunkt leitet auf `matrix-proxy:8080`.

## Hinweise

- `compose.override.private.yml` und `compose.override.public.yml` sind alternative Overlays und sollten nicht gemeinsam geladen werden.
- Docker-spezifische Mechanismen aus der Legacy-Datei wie `include`, `!reset` und `host-gateway` wurden bewusst entfernt, damit die Dateien für Podman Compose standardnäher bleiben.
- Für öffentliche Exposition setzt [compose.override.public.yml](/home/alex/Programme/Container/Selatrix/Kern/compose/compose.override.public.yml) weiterhin eine vorhandene [Caddyfile](/home/alex/Programme/Container/Selatrix/Kern/Caddyfile) und ein Verzeichnis [caddy-addon](/home/alex/Programme/Container/Selatrix/Kern/caddy-addon) voraus.
- [compose.override.supabase.yml](/home/alex/Programme/Container/Selatrix/Kern/compose/compose.override.supabase.yml) ist aktuell nur ein Platzhalter, weil die Supabase-Compose-Dateien laut Plan noch direkt ins Projekt übernommen werden müssen.
- Der Tailscale-Auth-Key gehoert in `.env` oder eine spaetere Secret-Verwaltung und darf nicht in diese README oder Compose-Dateien geschrieben werden.
- Nach dem ersten erfolgreichen Matrix-Start koennen Admin- und Bot-Nutzer im Synapse-Container angelegt werden:

```sh
podman exec -it matrix-synapse sh -lc 'register_new_matrix_user -u alexander -a -k "$MATRIX_REGISTRATION_SHARED_SECRET" http://localhost:8008'
podman exec -it matrix-synapse sh -lc 'register_new_matrix_user -u selatrix -k "$MATRIX_REGISTRATION_SHARED_SECRET" http://localhost:8008'
```
