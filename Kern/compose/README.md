# Compose layout

Die Dateien in diesem Ordner sind für `podman compose` als zusammensetzbare Teilstücke gedacht.
Alle Bind-Mount-Pfade sind relativ zu [compose.yml](/home/alex/Programme/Container/N8nAnwendung/compose/compose.yml) und zeigen deshalb mit `../` ins Projektwurzelverzeichnis.

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

## Hinweise

- `compose.override.private.yml` und `compose.override.public.yml` sind alternative Overlays und sollten nicht gemeinsam geladen werden.
- Docker-spezifische Mechanismen aus der Legacy-Datei wie `include`, `!reset` und `host-gateway` wurden bewusst entfernt, damit die Dateien für Podman Compose standardnäher bleiben.
- Für öffentliche Exposition setzt [compose.override.public.yml](/home/alex/Programme/Container/N8nAnwendung/compose/compose.override.public.yml) weiterhin eine vorhandene [Caddyfile](/home/alex/Programme/Container/N8nAnwendung/Caddyfile) und ein Verzeichnis [caddy-addon](/home/alex/Programme/Container/N8nAnwendung/caddy-addon) voraus.
- [compose.override.supabase.yml](/home/alex/Programme/Container/N8nAnwendung/compose/compose.override.supabase.yml) ist aktuell nur ein Platzhalter, weil die Supabase-Compose-Dateien laut Plan noch direkt ins Projekt übernommen werden müssen.
