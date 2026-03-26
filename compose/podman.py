from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from compose.env import Umgebungsvariablen

PROJEKT_NAME = "n8nanwendung"


@dataclass(frozen=True)
class PodmanComposeStartKonfiguration:
    dienst_ids: tuple[str, ...]
    compose_dateien: tuple[Path, ...]
    umgebungsvariablen: dict[str, str]

    def als_dict(self) -> dict[str, object]:
        return {
            "dienst_ids": list(self.dienst_ids),
            "compose_dateien": list(_serialisiere_compose_dateien(self.compose_dateien)),
            "umgebungsvariablen": dict(sorted(self.umgebungsvariablen.items())),
        }


def baue_startkonfiguration(
    dienst_ids: list[str],
    env_verwaltung: Umgebungsvariablen,
) -> PodmanComposeStartKonfiguration:
    fehlende_variablen = env_verwaltung.fehlende_pflichtvariablen(
        dienst_ids,
        entwurf_bevorzugen=False,
    )
    if fehlende_variablen:
        raise ValueError(
            "Fehlende Umgebungsvariablen: " + ", ".join(sorted(fehlende_variablen))
        )

    eindeutige_dienst_ids = tuple(sorted(set(dienst_ids)))
    return PodmanComposeStartKonfiguration(
        dienst_ids=eindeutige_dienst_ids,
        compose_dateien=Umgebungsvariablen.compose_dateien_fuer_dienste(eindeutige_dienst_ids),
        umgebungsvariablen=env_verwaltung.effektive_werte_fuer_dienste(
            eindeutige_dienst_ids,
            entwurf_bevorzugen=False,
        ),
    )


def podman_compose_argumente(
    konfiguration: PodmanComposeStartKonfiguration,
    *argumente: str,
) -> list[str]:
    befehl = ["compose", "-p", PROJEKT_NAME]
    for compose_datei in konfiguration.compose_dateien:
        befehl.extend(["-f", str(compose_datei)])
    befehl.extend(argumente)
    return befehl


def prozessumgebung_fuer_konfiguration(
    konfiguration: PodmanComposeStartKonfiguration,
) -> dict[str, str]:
    umgebung = os.environ.copy()
    umgebung.update(konfiguration.umgebungsvariablen)
    return umgebung


def speichere_startkonfiguration(
    pfad: Path,
    konfiguration: PodmanComposeStartKonfiguration,
) -> None:
    pfad.write_text(
        json.dumps(konfiguration.als_dict(), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def lade_startkonfiguration(pfad: Path) -> PodmanComposeStartKonfiguration | None:
    if not pfad.exists():
        return None

    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(daten, dict):
        return None

    dienst_ids = daten.get("dienst_ids")
    compose_dateien = daten.get("compose_dateien")
    umgebungsvariablen = daten.get("umgebungsvariablen")
    if not isinstance(dienst_ids, list) or not isinstance(compose_dateien, list):
        return None
    if not isinstance(umgebungsvariablen, dict):
        return None

    rekonstruierte_dateien: list[Path] = []
    for datei in compose_dateien:
        if not isinstance(datei, str) or not datei:
            return None
        rekonstruierte_dateien.append(_deserialisiere_compose_datei(datei))

    rekonstruierte_variablen: dict[str, str] = {}
    for name, wert in umgebungsvariablen.items():
        if not isinstance(name, str) or not isinstance(wert, str):
            return None
        rekonstruierte_variablen[name] = wert

    rekonstruierte_dienst_ids = []
    for dienst_id in dienst_ids:
        if not isinstance(dienst_id, str) or not dienst_id:
            return None
        rekonstruierte_dienst_ids.append(dienst_id)

    return PodmanComposeStartKonfiguration(
        dienst_ids=tuple(sorted(set(rekonstruierte_dienst_ids))),
        compose_dateien=tuple(rekonstruierte_dateien),
        umgebungsvariablen=rekonstruierte_variablen,
    )


def startkonfigurationen_unterscheiden_sich(
    links: PodmanComposeStartKonfiguration | None,
    rechts: PodmanComposeStartKonfiguration | None,
) -> bool:
    if links is None or rechts is None:
        return links != rechts
    return links.als_dict() != rechts.als_dict()


def loesche_startkonfiguration(pfad: Path) -> None:
    if pfad.exists():
        pfad.unlink()


def _serialisiere_compose_dateien(compose_dateien: tuple[Path, ...]) -> tuple[str, ...]:
    projektwurzel = Umgebungsvariablen.COMPOSE_VERZEICHNIS.parent
    serialisiert: list[str] = []
    for compose_datei in compose_dateien:
        try:
            serialisiert.append(str(compose_datei.resolve().relative_to(projektwurzel)))
        except ValueError:
            serialisiert.append(str(compose_datei.resolve()))
    return tuple(serialisiert)


def _deserialisiere_compose_datei(datei: str) -> Path:
    pfad = Path(datei)
    if pfad.is_absolute():
        return pfad
    return (Umgebungsvariablen.COMPOSE_VERZEICHNIS.parent / pfad).resolve()
