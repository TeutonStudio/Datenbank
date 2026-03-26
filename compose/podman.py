from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compose.env import Umgebungsvariablen


@dataclass(frozen=True)
class PodmanComposeStartKonfiguration:
    compose_dateien: tuple[Path, ...]
    umgebungsvariablen: dict[str, str]


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

    return PodmanComposeStartKonfiguration(
        compose_dateien=Umgebungsvariablen.compose_dateien_fuer_dienste(dienst_ids),
        umgebungsvariablen=env_verwaltung.effektive_werte_fuer_dienste(
            dienst_ids,
            entwurf_bevorzugen=False,
        ),
    )
