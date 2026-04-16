from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
import os
from pathlib import Path

from Kern.compose.env import Umgebungsvariablen

PROJEKT_NAME = "n8nanwendung"
_AUSGEWAEHLTE_DIENSTE_SCHLUESSEL = "ausgewaehlte_dienst_ids"


@dataclass(frozen=True)
class PodmanComposeStartKonfiguration:
    dienst_ids: tuple[str, ...]
    compose_dateien: tuple[Path, ...]
    umgebungsvariablen: dict[str, str]
    profile: tuple[str, ...] = ()

    def als_dict(self) -> dict[str, object]:
        return {
            "dienst_ids": list(self.dienst_ids),
            "compose_dateien": list(_serialisiere_compose_dateien(self.compose_dateien)),
            "umgebungsvariablen": dict(sorted(self.umgebungsvariablen.items())),
            "profile": list(self.profile),
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
        profile=_compose_profile_fuer_dienste(eindeutige_dienst_ids),
    )


def podman_compose_argumente(
    konfiguration: PodmanComposeStartKonfiguration,
    *argumente: str,
) -> list[str]:
    befehl = ["compose", "-p", PROJEKT_NAME]
    for profil in konfiguration.profile:
        befehl.extend(["--profile", profil])
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
    daten = _lade_status_daten(pfad)
    daten.update(konfiguration.als_dict())
    daten[_AUSGEWAEHLTE_DIENSTE_SCHLUESSEL] = list(
        _eindeutige_dienst_ids(konfiguration.dienst_ids)
    )
    _speichere_status_daten(pfad, daten)


def lade_startkonfiguration(pfad: Path) -> PodmanComposeStartKonfiguration | None:
    daten = _lade_status_daten(pfad)
    if not daten:
        return None

    dienst_ids = daten.get("dienst_ids")
    compose_dateien = daten.get("compose_dateien")
    umgebungsvariablen = daten.get("umgebungsvariablen")
    profile = daten.get("profile", [])
    if not isinstance(dienst_ids, list) or not isinstance(compose_dateien, list):
        return None
    if not isinstance(umgebungsvariablen, dict):
        return None
    if not isinstance(profile, list):
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

    rekonstruierte_profile = []
    for profil in profile:
        if not isinstance(profil, str) or not profil:
            return None
        rekonstruierte_profile.append(profil)

    return PodmanComposeStartKonfiguration(
        dienst_ids=tuple(sorted(set(rekonstruierte_dienst_ids))),
        compose_dateien=tuple(rekonstruierte_dateien),
        umgebungsvariablen=rekonstruierte_variablen,
        profile=tuple(
            sorted(
                set(rekonstruierte_profile).union(
                    _compose_profile_fuer_dienste(rekonstruierte_dienst_ids)
                )
            )
        ),
    )


def startkonfigurationen_unterscheiden_sich(
    links: PodmanComposeStartKonfiguration | None,
    rechts: PodmanComposeStartKonfiguration | None,
) -> bool:
    if links is None or rechts is None:
        return links != rechts
    return links.als_dict() != rechts.als_dict()


def loesche_startkonfiguration(pfad: Path) -> None:
    daten = _lade_status_daten(pfad)
    if not daten:
        if pfad.exists():
            pfad.unlink()
        return

    for schluessel in ("dienst_ids", "compose_dateien", "umgebungsvariablen", "profile"):
        daten.pop(schluessel, None)

    if daten:
        _speichere_status_daten(pfad, daten)
    elif pfad.exists():
        pfad.unlink()


def speichere_ausgewaehlte_dienste(
    pfad: Path,
    dienst_ids: Iterable[str],
) -> None:
    daten = _lade_status_daten(pfad)
    daten[_AUSGEWAEHLTE_DIENSTE_SCHLUESSEL] = list(_eindeutige_dienst_ids(dienst_ids))
    _speichere_status_daten(pfad, daten)


def lade_ausgewaehlte_dienste(pfad: Path) -> tuple[str, ...] | None:
    daten = _lade_status_daten(pfad)
    if not daten:
        return None

    dienst_ids = daten.get(_AUSGEWAEHLTE_DIENSTE_SCHLUESSEL, daten.get("dienst_ids"))
    if not isinstance(dienst_ids, list):
        return None

    rekonstruierte_dienst_ids = []
    for dienst_id in dienst_ids:
        if not isinstance(dienst_id, str) or not dienst_id:
            return None
        rekonstruierte_dienst_ids.append(dienst_id)

    return _eindeutige_dienst_ids(rekonstruierte_dienst_ids)


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


def _lade_status_daten(pfad: Path) -> dict[str, object]:
    if not pfad.exists():
        return {}

    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    return daten if isinstance(daten, dict) else {}


def _speichere_status_daten(pfad: Path, daten: dict[str, object]) -> None:
    pfad.write_text(
        json.dumps(daten, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _eindeutige_dienst_ids(dienst_ids: Iterable[str]) -> tuple[str, ...]:
    einzigartige_dienst_ids: list[str] = []
    bekannte_dienst_ids: set[str] = set()
    for dienst_id in dienst_ids:
        if not dienst_id or dienst_id in bekannte_dienst_ids:
            continue
        bekannte_dienst_ids.add(dienst_id)
        einzigartige_dienst_ids.append(dienst_id)
    return tuple(einzigartige_dienst_ids)


def _compose_profile_fuer_dienste(dienst_ids: Iterable[str]) -> tuple[str, ...]:
    profile: list[str] = []
    for dienst_id in dienst_ids:
        if dienst_id == "ollama" and "gpu-amd" not in profile:
            profile.append("gpu-amd")
    return tuple(profile)
