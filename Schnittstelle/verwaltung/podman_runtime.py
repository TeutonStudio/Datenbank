from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import subprocess
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


@dataclass(frozen=True)
class HintergrundFehler:
    meldung: str


class HintergrundWorker(QObject):
    fertig = pyqtSignal(object)

    def __init__(self, funktion: Callable[[], object]):
        super().__init__()
        self._funktion = funktion

    @pyqtSlot()
    def ausfuehren(self) -> None:
        try:
            self.fertig.emit(self._funktion())
        except Exception as fehler:
            self.fertig.emit(HintergrundFehler(str(fehler)))


def fuehre_podman_kommando(
    projekt_pfad: Path,
    argumente: list[str],
    *,
    umgebung: dict[str, str] | None = None,
    timeout: int = 15,
    timeout_meldung: str = "Die Podman-Abfrage hat das Zeitlimit überschritten.",
    nicht_gefunden_meldung: str = "Podman wurde nicht gefunden.",
    fehler_meldung: str = "Die Podman-Abfrage ist fehlgeschlagen.",
) -> tuple[str, str]:
    try:
        ergebnis = subprocess.run(
            ["podman", *argumente],
            cwd=projekt_pfad,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=umgebung,
        )
    except FileNotFoundError:
        return "", nicht_gefunden_meldung
    except subprocess.TimeoutExpired:
        return "", timeout_meldung
    except KeyboardInterrupt:
        return "", "Die Podman-Abfrage wurde abgebrochen."

    stdout = ergebnis.stdout.strip()
    stderr = ergebnis.stderr.strip()
    if ergebnis.returncode != 0:
        return "", stderr or stdout or fehler_meldung
    return stdout, ""


def lade_json_liste(
    projekt_pfad: Path,
    basis_befehl: list[str],
    *,
    timeout: int,
) -> tuple[list[dict[str, Any]], str]:
    daten, fehler = fuehre_podman_kommando(
        projekt_pfad,
        [*basis_befehl, "--format", "json"],
        timeout=timeout,
    )
    if daten:
        try:
            geparst = json.loads(daten)
            if isinstance(geparst, list):
                return geparst, ""
            if isinstance(geparst, dict):
                return [geparst], ""
        except json.JSONDecodeError:
            pass
    elif fehler and "format" not in fehler.lower():
        return [], fehler

    daten, fehler = fuehre_podman_kommando(
        projekt_pfad,
        [*basis_befehl, "--format", "{{json .}}"],
        timeout=timeout,
    )
    if not daten:
        return [], fehler

    zeilen = []
    for zeile in daten.splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            zeilen.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return zeilen, fehler if not zeilen else ""
