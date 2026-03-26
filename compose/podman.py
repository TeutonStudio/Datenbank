from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Iterable


COMPOSE_VERZEICHNIS = Path(__file__).resolve().parent

# Zentrale Zuordnung: welcher Dienst welche Compose-Teilstücke benötigt.
DIENST_COMPOSE_DATEIEN: dict[str, tuple[str, ...]] = {
    "n8n": (
        "compose.override.n8n-db.yml",
        "compose.override.n8n.yml",
    ),
    "open-webui": ("compose.override.open-webui.yml",),
    "flowise": ("compose.override.flowise.yml",),
    "langfuse": (
        "compose.override.langfuse-postgres.yml",
        "compose.override.clickhouse.yml",
        "compose.override.minio.yml",
        "compose.override.redis.yml",
        "compose.override.langfuse.yml",
    ),
    "neo4j": ("compose.override.neo4j.yml",),
    "minio": ("compose.override.minio.yml",),
    "searxng": ("compose.override.searxng.yml",),
    "supabase": ("compose.override.supabase.yml",),
    "ollama": ("compose.override.ollama.yml",),
}

_VARIABLE_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?:(:?[-+?])([^}]*))?\}")


@dataclass(frozen=True)
class ComposeVariable:
    name: str
    hat_standardwert: bool = False
    standardwert: str | None = None
    dateien: tuple[str, ...] = ()


DIENST_ZUSAETZLICHE_VARIABLEN: dict[str, tuple[ComposeVariable, ...]] = {
    "n8n": (
        ComposeVariable("N8N_ENCRYPTION_KEY"),
        ComposeVariable("N8N_USER_MANAGEMENT_JWT_SECRET"),
    ),
    "open-webui": (
        ComposeVariable("WEBUI_HOSTNAME", hat_standardwert=True, standardwert=":8002"),
    ),
    "flowise": (
        ComposeVariable("FLOWISE_HOSTNAME", hat_standardwert=True, standardwert=":8003"),
    ),
    "langfuse": (
        ComposeVariable("LANGFUSE_HOSTNAME", hat_standardwert=True, standardwert=":8007"),
    ),
    "neo4j": (
        ComposeVariable("NEO4J_HOSTNAME", hat_standardwert=True, standardwert=":8008"),
    ),
    "minio": (),
    "searxng": (),
    "supabase": (
        ComposeVariable("SUPABASE_HOSTNAME", hat_standardwert=True, standardwert=":8005"),
    ),
    "ollama": (
        ComposeVariable("OLLAMA_HOSTNAME", hat_standardwert=True, standardwert=":8004"),
    ),
}


# TODO Umgebungsvariablen als eigene Klasse
def _extrahiere_variablen_aus_datei(datei_name: str) -> dict[str, ComposeVariable]:
    pfad = COMPOSE_VERZEICHNIS / datei_name
    inhalt = pfad.read_text(encoding="utf-8")

    variablen: dict[str, dict[str, object]] = {}
    for zeile in inhalt.splitlines():
        for treffer in _VARIABLE_PATTERN.finditer(zeile):
            variablenname = treffer.group(1)
            operator = treffer.group(2) or ""
            standardwert = treffer.group(3)

            eintrag = variablen.setdefault(
                variablenname,
                {
                    "hat_standardwert": False,
                    "standardwert": None,
                    "dateien": set(),
                },
            )
            if operator in {"-", ":-"}:
                eintrag["hat_standardwert"] = True
                if eintrag["standardwert"] is None:
                    eintrag["standardwert"] = standardwert
            eintrag["dateien"].add(datei_name)

    return {
        variablenname: ComposeVariable(
            name=variablenname,
            hat_standardwert=bool(daten["hat_standardwert"]),
            standardwert=(
                str(daten["standardwert"])
                if daten["standardwert"] is not None
                else None
            ),
            dateien=tuple(sorted(str(datei) for datei in daten["dateien"])),
        )
        for variablenname, daten in variablen.items()
    }


def _variablen_aus_dateien(dateien: Iterable[str]) -> tuple[ComposeVariable, ...]:
    zusammengefuehrt: dict[str, dict[str, object]] = {}

    for datei_name in dateien:
        for variablenname, variable in _extrahiere_variablen_aus_datei(datei_name).items():
            eintrag = zusammengefuehrt.setdefault(
                variablenname,
                {
                    "hat_standardwert": False,
                    "standardwert": None,
                    "dateien": set(),
                },
            )
            eintrag["hat_standardwert"] = (
                bool(eintrag["hat_standardwert"]) or variable.hat_standardwert
            )
            if eintrag["standardwert"] is None and variable.standardwert is not None:
                eintrag["standardwert"] = variable.standardwert
            eintrag["dateien"].update(variable.dateien)

    return tuple(
        ComposeVariable(
            name=variablenname,
            hat_standardwert=bool(daten["hat_standardwert"]),
            standardwert=(
                str(daten["standardwert"])
                if daten["standardwert"] is not None
                else None
            ),
            dateien=tuple(sorted(str(datei) for datei in daten["dateien"])),
        )
        for variablenname, daten in sorted(zusammengefuehrt.items())
    )


def _fuege_zusatzvariablen_hinzu(
    basis_variablen: tuple[ComposeVariable, ...],
    zusatzvariablen: Iterable[ComposeVariable],
) -> tuple[ComposeVariable, ...]:
    zusammengefuehrt = {variable.name: variable for variable in basis_variablen}

    for variable in zusatzvariablen:
        vorhanden = zusammengefuehrt.get(variable.name)
        if vorhanden is None:
            zusammengefuehrt[variable.name] = variable
            continue

        zusammengefuehrt[variable.name] = ComposeVariable(
            name=vorhanden.name,
            hat_standardwert=vorhanden.hat_standardwert or variable.hat_standardwert,
            standardwert=vorhanden.standardwert or variable.standardwert,
            dateien=tuple(sorted(set(vorhanden.dateien).union(variable.dateien))),
        )

    return tuple(sorted(zusammengefuehrt.values(), key=lambda variable: variable.name))


@lru_cache(maxsize=1)
def lade_dienst_variablen() -> dict[str, tuple[ComposeVariable, ...]]:
    return {
        dienst_id: _fuege_zusatzvariablen_hinzu(
            _variablen_aus_dateien(dateien),
            DIENST_ZUSAETZLICHE_VARIABLEN.get(dienst_id, ()),
        )
        for dienst_id, dateien in DIENST_COMPOSE_DATEIEN.items()
    }
