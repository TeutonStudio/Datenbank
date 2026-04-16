from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class UmgebungsvariableDefinition:
    name: str
    dienst_ids: tuple[str, ...] = ()
    hat_standardwert: bool = False
    standardwert: str | None = None
    dateien: tuple[str, ...] = ()


@dataclass(frozen=True)
class Umgebungsvariable:
    name: str
    wert: str = ""
    dienst_ids: tuple[str, ...] = ()
    hat_standardwert: bool = False
    standardwert: str | None = None
    dateien: tuple[str, ...] = ()

    @property
    def ist_manuell(self) -> bool:
        return not self.dienst_ids

    @property
    def ist_definiert(self) -> bool:
        return self.wert != ""

    def effektiver_wert(self) -> str | None:
        if self.wert != "":
            return self.wert
        if self.hat_standardwert and self.standardwert is not None:
            return self.standardwert
        return None


class Umgebungsvariablen:
    COMPOSE_VERZEICHNIS = Path(__file__).resolve().parent

    # Zentrale Zuordnung: welcher Dienst welche Compose-Teilstuecke und damit
    # welche Umgebungsvariablen benoetigt.
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
        "immich": ("compose.override.immich.yml",),
    }

    DIENST_ZUSAETZLICHE_DEFINITIONEN: dict[str, tuple[UmgebungsvariableDefinition, ...]] = {
        "n8n": (
            UmgebungsvariableDefinition("N8N_ENCRYPTION_KEY", dienst_ids=("n8n",)),
            UmgebungsvariableDefinition(
                "N8N_USER_MANAGEMENT_JWT_SECRET",
                dienst_ids=("n8n",),
            ),
        ),
        "open-webui": (
            UmgebungsvariableDefinition(
                "WEBUI_HOSTNAME",
                dienst_ids=("open-webui",),
                hat_standardwert=True,
                standardwert=":8002",
            ),
        ),
        "flowise": (
            UmgebungsvariableDefinition(
                "FLOWISE_HOSTNAME",
                dienst_ids=("flowise",),
                hat_standardwert=True,
                standardwert=":8003",
            ),
        ),
        "langfuse": (
            UmgebungsvariableDefinition(
                "LANGFUSE_HOSTNAME",
                dienst_ids=("langfuse",),
                hat_standardwert=True,
                standardwert=":8007",
            ),
        ),
        "neo4j": (
            # UmgebungsvariableDefinition("NEO4J_USER", dienst_ids=("neo4j",)),
            UmgebungsvariableDefinition("NEO4J_PASSWORD", dienst_ids=("neo4j",)),
            UmgebungsvariableDefinition(
                "NEO4J_HOSTNAME",
                dienst_ids=("neo4j",),
                hat_standardwert=True,
                standardwert=":8008",
            ),
        ),
        "minio": (),
        "searxng": (),
        "supabase": (
            UmgebungsvariableDefinition(
                "SUPABASE_HOSTNAME",
                dienst_ids=("supabase",),
                hat_standardwert=True,
                standardwert=":8005",
            ),
        ),
        "ollama": (
            UmgebungsvariableDefinition(
                "OLLAMA_HOSTNAME",
                dienst_ids=("ollama",),
                hat_standardwert=True,
                standardwert=":8004",
            ),
        ),
        "immich": (
            UmgebungsvariableDefinition(
                "IMMICH_HOSTNAME",
                dienst_ids=("immich",),
                hat_standardwert=True,
                standardwert=":8009",
            ),
            UmgebungsvariableDefinition(
                "IMMICH_PRIVATE_PORT",
                dienst_ids=("immich",),
                hat_standardwert=True,
                standardwert="2283",
            ),
        ),
    }

    _VARIABLE_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?:(:?[-+?])([^}]*))?\}")
    _ABGELEITETE_VARIABLEN = {"NEO4J_AUTH"}

    def __init__(self, env_pfad: Path, cache_pfad: Path):
        self._env_pfad = env_pfad
        self._cache_pfad = cache_pfad

    @property
    def env_pfad(self) -> Path:
        return self._env_pfad

    @property
    def cache_pfad(self) -> Path:
        return self._cache_pfad

    @classmethod
    def compose_dateien_fuer_dienste(cls, dienst_ids: Iterable[str]) -> tuple[Path, ...]:
        dateien: list[Path] = [cls.COMPOSE_VERZEICHNIS / "compose.yml"]
        bekannte_pfade = {dateien[0]}

        for dienst_id in dienst_ids:
            for datei_name in cls.DIENST_COMPOSE_DATEIEN.get(dienst_id, ()):
                pfad = cls.COMPOSE_VERZEICHNIS / datei_name
                if pfad in bekannte_pfade:
                    continue
                bekannte_pfade.add(pfad)
                dateien.append(pfad)

        return tuple(dateien)

    @classmethod
    @lru_cache(maxsize=1)
    def definitionen_nach_dienst(cls) -> dict[str, tuple[UmgebungsvariableDefinition, ...]]:
        definitionen_nach_dienst: dict[str, tuple[UmgebungsvariableDefinition, ...]] = {}

        for dienst_id, dateien in cls.DIENST_COMPOSE_DATEIEN.items():
            basis_definitionen = cls._definitionen_aus_dateien(dienst_id, dateien)
            definitionen_nach_dienst[dienst_id] = cls._fuege_zusatzdefinitionen_hinzu(
                basis_definitionen,
                cls.DIENST_ZUSAETZLICHE_DEFINITIONEN.get(dienst_id, ()),
            )

        return definitionen_nach_dienst

    def definitionen_fuer_dienste(
        self,
        dienst_ids: Iterable[str],
    ) -> dict[str, UmgebungsvariableDefinition]:
        zusammengefuehrt: dict[str, UmgebungsvariableDefinition] = {}

        for dienst_id in dienst_ids:
            for definition in self.definitionen_nach_dienst().get(dienst_id, ()):
                vorhanden = zusammengefuehrt.get(definition.name)
                if vorhanden is None:
                    zusammengefuehrt[definition.name] = definition
                    continue

                dienstemenge = tuple(
                    sorted(set(vorhanden.dienst_ids).union(definition.dienst_ids))
                )
                dateimenge = tuple(sorted(set(vorhanden.dateien).union(definition.dateien)))
                zusammengefuehrt[definition.name] = UmgebungsvariableDefinition(
                    name=definition.name,
                    dienst_ids=dienstemenge,
                    hat_standardwert=(
                        vorhanden.hat_standardwert or definition.hat_standardwert
                    ),
                    standardwert=vorhanden.standardwert or definition.standardwert,
                    dateien=dateimenge,
                )

        return zusammengefuehrt

    def variablen_fuer_dienste(
        self,
        dienst_ids: Iterable[str],
        *,
        entwurf_bevorzugen: bool = True,
    ) -> list[Umgebungsvariable]:
        definitionen_nach_name = self.definitionen_fuer_dienste(dienst_ids)
        geladene_variablen = (
            self._lade_zeilen(self._cache_pfad)
            if entwurf_bevorzugen and self._cache_pfad.exists()
            else self._lade_zeilen(self._env_pfad)
        )
        geladene_variablen = self._normalisiere_geladene_variablen(
            geladene_variablen,
            definitionen_nach_name,
        )

        variablen: list[Umgebungsvariable] = []
        vorhandene_namen: set[str] = set()
        for geladene_variable in geladene_variablen:
            definition = definitionen_nach_name.get(geladene_variable.name)
            if definition is None:
                variablen.append(geladene_variable)
            else:
                variablen.append(
                    Umgebungsvariable(
                        name=geladene_variable.name,
                        wert=geladene_variable.wert,
                        dienst_ids=definition.dienst_ids,
                        hat_standardwert=definition.hat_standardwert,
                        standardwert=definition.standardwert,
                        dateien=definition.dateien,
                    )
                )
            if geladene_variable.name:
                vorhandene_namen.add(geladene_variable.name)

        for name, definition in definitionen_nach_name.items():
            if name in vorhandene_namen:
                continue
            variablen.append(
                Umgebungsvariable(
                    name=name,
                    wert="",
                    dienst_ids=definition.dienst_ids,
                    hat_standardwert=definition.hat_standardwert,
                    standardwert=definition.standardwert,
                    dateien=definition.dateien,
                )
            )

        return variablen

    def speichere_entwurf(self, variablen: Iterable[Umgebungsvariable]) -> None:
        self._schreibe_zeilen(self._cache_pfad, variablen)

    def verwerfe_entwurf(self) -> None:
        if self._cache_pfad.exists():
            self._cache_pfad.unlink()

    def speichere_env(self, variablen: Iterable[Umgebungsvariable]) -> None:
        self._schreibe_env(self._env_pfad, variablen)
        self.verwerfe_entwurf()

    def fehlende_pflichtvariablen(
        self,
        dienst_ids: Iterable[str],
        *,
        entwurf_bevorzugen: bool = False,
    ) -> list[str]:
        fehlende_variablen: list[str] = []
        for variable in self.variablen_fuer_dienste(
            dienst_ids,
            entwurf_bevorzugen=entwurf_bevorzugen,
        ):
            if not variable.name or variable.ist_manuell:
                continue
            if variable.ist_definiert or variable.hat_standardwert:
                continue
            fehlende_variablen.append(variable.name)
        return fehlende_variablen

    def effektive_werte_fuer_dienste(
        self,
        dienst_ids: Iterable[str],
        *,
        entwurf_bevorzugen: bool = False,
    ) -> dict[str, str]:
        dienst_id_menge = set(dienst_ids)
        werte: dict[str, str] = {}
        for variable in self.variablen_fuer_dienste(
            dienst_id_menge,
            entwurf_bevorzugen=entwurf_bevorzugen,
        ):
            if not variable.name:
                continue
            effektiver_wert = variable.effektiver_wert()
            if effektiver_wert is None:
                continue
            werte[variable.name] = effektiver_wert

        if "neo4j" in dienst_id_menge:
            # neo4j_user = werte.get("NEO4J_USER")
            neo4j_user = "neo4j"
            neo4j_passwort = werte.get("NEO4J_PASSWORD")
            if neo4j_user and neo4j_passwort:
                werte["NEO4J_AUTH"] = f"{neo4j_user}/{neo4j_passwort}"
        return werte

    @classmethod
    def _definitionen_aus_dateien(
        cls,
        dienst_id: str,
        dateien: Iterable[str],
    ) -> tuple[UmgebungsvariableDefinition, ...]:
        zusammengefuehrt: dict[str, UmgebungsvariableDefinition] = {}

        for datei_name in dateien:
            for name, definition in cls._extrahiere_definitionen_aus_datei(
                dienst_id,
                datei_name,
            ).items():
                vorhanden = zusammengefuehrt.get(name)
                if vorhanden is None:
                    zusammengefuehrt[name] = definition
                    continue

                zusammengefuehrt[name] = UmgebungsvariableDefinition(
                    name=name,
                    dienst_ids=tuple(sorted(set(vorhanden.dienst_ids).union(definition.dienst_ids))),
                    hat_standardwert=(
                        vorhanden.hat_standardwert or definition.hat_standardwert
                    ),
                    standardwert=vorhanden.standardwert or definition.standardwert,
                    dateien=tuple(sorted(set(vorhanden.dateien).union(definition.dateien))),
                )

        return tuple(
            definition
            for _name, definition in sorted(zusammengefuehrt.items())
        )

    @classmethod
    def _extrahiere_definitionen_aus_datei(
        cls,
        dienst_id: str,
        datei_name: str,
    ) -> dict[str, UmgebungsvariableDefinition]:
        inhalt = (cls.COMPOSE_VERZEICHNIS / datei_name).read_text(encoding="utf-8")
        definitionen: dict[str, UmgebungsvariableDefinition] = {}

        for zeile in inhalt.splitlines():
            for treffer in cls._VARIABLE_PATTERN.finditer(zeile):
                name = treffer.group(1)
                if name in cls._ABGELEITETE_VARIABLEN:
                    continue
                operator = treffer.group(2) or ""
                standardwert = treffer.group(3)
                vorhanden = definitionen.get(name)
                definition = UmgebungsvariableDefinition(
                    name=name,
                    dienst_ids=(dienst_id,),
                    hat_standardwert=operator in {"-", ":-"},
                    standardwert=standardwert if operator in {"-", ":-"} else None,
                    dateien=(datei_name,),
                )
                if vorhanden is None:
                    definitionen[name] = definition
                    continue

                definitionen[name] = UmgebungsvariableDefinition(
                    name=name,
                    dienst_ids=tuple(sorted(set(vorhanden.dienst_ids).union(definition.dienst_ids))),
                    hat_standardwert=(
                        vorhanden.hat_standardwert or definition.hat_standardwert
                    ),
                    standardwert=vorhanden.standardwert or definition.standardwert,
                    dateien=tuple(sorted(set(vorhanden.dateien).union(definition.dateien))),
                )

        return definitionen

    @staticmethod
    def _fuege_zusatzdefinitionen_hinzu(
        basis_definitionen: tuple[UmgebungsvariableDefinition, ...],
        zusatzdefinitionen: Iterable[UmgebungsvariableDefinition],
    ) -> tuple[UmgebungsvariableDefinition, ...]:
        zusammengefuehrt = {definition.name: definition for definition in basis_definitionen}

        for definition in zusatzdefinitionen:
            vorhanden = zusammengefuehrt.get(definition.name)
            if vorhanden is None:
                zusammengefuehrt[definition.name] = definition
                continue

            zusammengefuehrt[definition.name] = UmgebungsvariableDefinition(
                name=definition.name,
                dienst_ids=tuple(sorted(set(vorhanden.dienst_ids).union(definition.dienst_ids))),
                hat_standardwert=(
                    vorhanden.hat_standardwert or definition.hat_standardwert
                ),
                standardwert=vorhanden.standardwert or definition.standardwert,
                dateien=tuple(sorted(set(vorhanden.dateien).union(definition.dateien))),
            )

        return tuple(
            definition
            for _name, definition in sorted(zusammengefuehrt.items())
        )

    @classmethod
    def _normalisiere_geladene_variablen(
        cls,
        geladene_variablen: list[Umgebungsvariable],
        definitionen_nach_name: dict[str, UmgebungsvariableDefinition],
    ) -> list[Umgebungsvariable]:
        vorhandene_namen = {variable.name for variable in geladene_variablen}
        ergaenzte_variablen: list[Umgebungsvariable] = []

        for variable in geladene_variablen:
            if variable.name in cls._ABGELEITETE_VARIABLEN:
                cls._ergaenze_neo4j_zugang_aus_auth(
                    variable.wert,
                    vorhandene_namen,
                    ergaenzte_variablen,
                    definitionen_nach_name,
                )
                continue
            ergaenzte_variablen.append(variable)

        return ergaenzte_variablen

    @staticmethod
    def _ergaenze_neo4j_zugang_aus_auth(
        neo4j_auth: str,
        vorhandene_namen: set[str],
        variablen: list[Umgebungsvariable],
        definitionen_nach_name: dict[str, UmgebungsvariableDefinition],
    ) -> None:
        if "/" not in neo4j_auth:
            return

        benutzer, passwort = neo4j_auth.split("/", 1)
        werte = {
            "NEO4J_USER": benutzer,
            "NEO4J_PASSWORD": passwort,
        }
        for name, wert in werte.items():
            if name in vorhandene_namen:
                continue
            definition = definitionen_nach_name.get(name)
            if definition is None:
                variablen.append(Umgebungsvariable(name=name, wert=wert))
                continue
            variablen.append(
                Umgebungsvariable(
                    name=name,
                    wert=wert,
                    dienst_ids=definition.dienst_ids,
                    hat_standardwert=definition.hat_standardwert,
                    standardwert=definition.standardwert,
                    dateien=definition.dateien,
                )
            )

    @staticmethod
    def _lade_zeilen(pfad: Path) -> list[Umgebungsvariable]:
        if not pfad.exists():
            return []

        if pfad.suffix == ".json":
            try:
                daten = json.loads(pfad.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []

            if not isinstance(daten, list):
                return []

            variablen: list[Umgebungsvariable] = []
            for eintrag in daten:
                if not isinstance(eintrag, dict):
                    continue
                name = str(eintrag.get("name") or "").strip()
                wert = str(eintrag.get("wert") or "")
                if not name and not wert:
                    continue
                variablen.append(Umgebungsvariable(name=name, wert=wert))
            return variablen

        variablen = []
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            name, wert = zeile.split("=", 1)
            name = name.strip()
            if not name:
                continue
            variablen.append(Umgebungsvariable(name=name, wert=wert))
        return variablen

    @staticmethod
    def _schreibe_zeilen(pfad: Path, variablen: Iterable[Umgebungsvariable]) -> None:
        daten = []
        for variable in variablen:
            if variable.name in Umgebungsvariablen._ABGELEITETE_VARIABLEN:
                continue
            if not variable.name and not variable.wert:
                continue
            daten.append(
                {
                    "name": variable.name,
                    "wert": variable.wert,
                }
            )

        if not daten:
            if pfad.exists():
                pfad.unlink()
            return

        pfad.write_text(
            json.dumps(daten, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _schreibe_env(pfad: Path, variablen: Iterable[Umgebungsvariable]) -> None:
        zeilen = []
        for variable in variablen:
            if variable.name in Umgebungsvariablen._ABGELEITETE_VARIABLEN:
                continue
            if not variable.name and not variable.wert:
                continue
            zeilen.append(f"{variable.name}={variable.wert}")

        inhalt = "\n".join(zeilen)
        if inhalt:
            inhalt = f"{inhalt}\n"
        pfad.write_text(inhalt, encoding="utf-8")


# Rueckwaertskompatibler Alias auf den alten Namen in Kleinbuchstaben.
# umgebungsvariablen = Umgebungsvariablen
