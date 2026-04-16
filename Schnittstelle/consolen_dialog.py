from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import shlex

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


AbgeschlossenCallback = Callable[[bool, str], None]

_ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_FORTSCHRITT_PATTERN = re.compile(
    r"(?P<prozent>\d{1,3}(?:[.,]\d+)?%)|"
    r"(?P<groesse>\d+(?:[.,]\d+)?\s?(?:B|kB|KB|MB|GB|TB)"
    r"(?:\s*/\s*\d+(?:[.,]\d+)?\s?(?:B|kB|KB|MB|GB|TB))?)"
)
_STATUS_WOERTER = (
    "Pulling",
    "Pulled",
    "Downloading",
    "Extracting",
    "Creating",
    "Created",
    "Recreate",
    "Recreating",
    "Recreated",
    "Starting",
    "Started",
    "Restarting",
    "Restarted",
    "Stopping",
    "Stopped",
    "Removing",
    "Removed",
    "Running",
    "Done",
    "Error",
)
_STATUS_PATTERN = re.compile(
    r"^(?P<objekt>.+?)\s+(?P<zustand>"
    + "|".join(re.escape(wort) for wort in _STATUS_WOERTER)
    + r")(?:\s+(?P<details>.*))?$",
    re.IGNORECASE,
)
_FEHLER_PATTERN = re.compile(
    r"\b(error|failed|failure|denied|not found|invalid|unable|cannot|could not|"
    r"timeout|timed out)\b",
    re.IGNORECASE,
)


@dataclass
class ProzessStatusEintrag:
    schluessel: str
    objekt: str
    typ: str
    zustand: str
    fortschritt: str = ""
    details: str = ""


@dataclass
class ParserErgebnis:
    eintraege: list[ProzessStatusEintrag]
    resttext: str = ""


class PodmanAusgabeParser:
    def __init__(self) -> None:
        self._puffer = ""
        self._argumente: list[str] = []
        self._befehl_label = "Podman"
        self._befehl_schluessel = "befehl:podman"
        self._ollama_modell: str | None = None
        self._podman_aktion: str | None = None
        self._podman_ziele: set[str] = set()

    def setze_befehl(
        self,
        argumente: list[str],
        befehl_label: str,
        befehl_schluessel: str,
    ) -> None:
        self._argumente = argumente
        self._befehl_label = befehl_label
        self._befehl_schluessel = befehl_schluessel
        self._ollama_modell = self._finde_ollama_modell(argumente)
        self._podman_aktion, self._podman_ziele = self._finde_podman_aktion(argumente)

    def verarbeite(self, text: str) -> ParserErgebnis:
        eintraege: list[ProzessStatusEintrag] = []
        rest: list[str] = []

        for zeichen in text:
            if zeichen in "\r\n":
                self._verarbeite_zeile(self._puffer, eintraege, rest)
                self._puffer = ""
                continue
            self._puffer += zeichen

        return ParserErgebnis(eintraege=eintraege, resttext="".join(rest))

    def abschliessen(self) -> ParserErgebnis:
        if not self._puffer:
            return ParserErgebnis(eintraege=[])

        eintraege: list[ProzessStatusEintrag] = []
        rest: list[str] = []
        self._verarbeite_zeile(self._puffer, eintraege, rest)
        self._puffer = ""
        return ParserErgebnis(eintraege=eintraege, resttext="".join(rest))

    def _verarbeite_zeile(
        self,
        rohzeile: str,
        eintraege: list[ProzessStatusEintrag],
        rest: list[str],
    ) -> None:
        zeile = _ANSI_PATTERN.sub("", rohzeile).strip()
        if not zeile:
            return

        if zeile.startswith("$ ") or zeile.startswith("## "):
            rest.append(f"{zeile}\n")
            return

        ollama_eintrag = self._parse_ollama_zeile(zeile)
        if ollama_eintrag is not None:
            eintraege.append(ollama_eintrag)
            return

        compose_eintrag = self._parse_status_zeile(zeile)
        if compose_eintrag is not None:
            eintraege.append(compose_eintrag)
            if compose_eintrag.zustand == "Error":
                rest.append(f"{zeile}\n")
            return

        ziel_eintrag = self._parse_podman_zielzeile(zeile)
        if ziel_eintrag is not None:
            eintraege.append(ziel_eintrag)
            return

        if _FEHLER_PATTERN.search(zeile):
            eintraege.append(
                ProzessStatusEintrag(
                    schluessel=self._befehl_schluessel,
                    objekt=self._befehl_label,
                    typ="Befehl",
                    zustand="Error",
                    details=zeile,
                )
            )
            rest.append(f"{zeile}\n")
            return

        rest.append(f"{zeile}\n")

    def _parse_ollama_zeile(self, zeile: str) -> ProzessStatusEintrag | None:
        if self._ollama_modell is None:
            return None

        text = zeile.lower()
        if not (
            text.startswith("pulling ")
            or text.startswith("verifying ")
            or text.startswith("writing ")
            or text == "success"
        ):
            return None

        modell = self._ollama_modell
        schluessel = f"ollama-modell:{modell}"
        fortschritt = _extrahiere_fortschritt(zeile)

        if text.startswith("pulling manifest"):
            return ProzessStatusEintrag(
                schluessel=schluessel,
                objekt=modell,
                typ="Modell",
                zustand="Pulling",
                fortschritt=fortschritt,
                details="Manifest",
            )

        if text.startswith("pulling "):
            digest = zeile.split(maxsplit=1)[1].split(maxsplit=1)[0]
            return ProzessStatusEintrag(
                schluessel=schluessel,
                objekt=modell,
                typ="Modell",
                zustand="Downloading" if fortschritt else "Pulling",
                fortschritt=fortschritt,
                details=f"Layer {digest}",
            )

        if text.startswith("verifying "):
            return ProzessStatusEintrag(
                schluessel=schluessel,
                objekt=modell,
                typ="Modell",
                zustand="Verifying",
                details=zeile,
            )

        if text.startswith("writing "):
            return ProzessStatusEintrag(
                schluessel=schluessel,
                objekt=modell,
                typ="Modell",
                zustand="Writing",
                details=zeile,
            )

        if text == "success":
            return ProzessStatusEintrag(
                schluessel=schluessel,
                objekt=modell,
                typ="Modell",
                zustand="Done",
            )

        return None

    def _parse_status_zeile(self, zeile: str) -> ProzessStatusEintrag | None:
        bereinigt = _bereinige_statuszeile(zeile)
        if bereinigt.lower().startswith(("running ", "done ")):
            fortschritt = _extrahiere_fortschritt(bereinigt)
            return ProzessStatusEintrag(
                schluessel=self._befehl_schluessel,
                objekt=self._befehl_label,
                typ="Befehl",
                zustand="Running",
                fortschritt=fortschritt,
                details=bereinigt,
            )

        treffer = _STATUS_PATTERN.match(bereinigt)
        if treffer is None:
            return None

        objekt_roh = treffer.group("objekt").strip()
        zustand = _normalisiere_zustand(treffer.group("zustand"))
        details = (treffer.group("details") or "").strip()
        objekt, typ = _klassifiziere_objekt(objekt_roh)
        fortschritt = _extrahiere_fortschritt(details)
        schluessel = f"{typ.lower()}:{objekt}"

        if _ist_image_layer(objekt):
            schluessel = "image:downloads"
            objekt = "Images"
            typ = "Image"
            details = f"{objekt_roh} {details}".strip()

        return ProzessStatusEintrag(
            schluessel=schluessel,
            objekt=objekt,
            typ=typ,
            zustand=zustand,
            fortschritt=fortschritt,
            details=details,
        )

    def _parse_podman_zielzeile(self, zeile: str) -> ProzessStatusEintrag | None:
        if self._podman_aktion is None or zeile not in self._podman_ziele:
            return None

        zustand = {
            "stop": "Stopped",
            "start": "Started",
            "restart": "Started",
            "rm": "Removed",
        }.get(self._podman_aktion, "Done")
        return ProzessStatusEintrag(
            schluessel=f"container:{zeile}",
            objekt=zeile,
            typ="Container",
            zustand=zustand,
        )

    def _finde_ollama_modell(self, argumente: list[str]) -> str | None:
        for index, argument in enumerate(argumente):
            if argument == "pull" and index + 1 < len(argumente):
                return argumente[index + 1]
        return None

    def _finde_podman_aktion(self, argumente: list[str]) -> tuple[str | None, set[str]]:
        if not argumente or argumente[0] == "compose":
            return None, set()

        aktion = argumente[0]
        if aktion not in {"stop", "start", "restart", "rm"}:
            return None, set()

        ziele = {argument for argument in argumente[1:] if not argument.startswith("-")}
        return aktion, ziele


class _PodmanAusgabeDialogBasis(QDialog):
    def _initialisiere_ausgabe_dialog(self, titel: str, status_text: str) -> None:
        self._ausgabe: list[str] = []
        self._abgeschlossen_callback: AbgeschlossenCallback | None = None
        self._parser = PodmanAusgabeParser()
        self._status_zeilen: dict[str, int] = {}
        self._befehl_nummer = 0
        self._aktueller_befehl_schluessel = "befehl:podman"
        self._aktueller_befehl_label = "Podman"

        self.setWindowTitle(titel)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(980, 620)

        layout = QVBoxLayout(self)
        self.status_label = QLabel(status_text, self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        layout.addWidget(splitter, 1)

        self.status_tabelle = QTableWidget(0, 5, self)
        self.status_tabelle.setHorizontalHeaderLabels(
            ["Objekt", "Typ", "Zustand", "Fortschritt", "Details"]
        )
        self.status_tabelle.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.status_tabelle.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.status_tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_tabelle.setAlternatingRowColors(True)
        self.status_tabelle.verticalHeader().setVisible(False)

        header = self.status_tabelle.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.status_tabelle)

        self.ausgabe_feld = QPlainTextEdit(self)
        self.ausgabe_feld.setReadOnly(True)
        self.ausgabe_feld.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.ausgabe_feld.setMaximumBlockCount(2000)
        splitter.addWidget(self.ausgabe_feld)
        splitter.setSizes([360, 180])

        aktionen = QHBoxLayout()
        aktionen.addStretch()
        self.abbrechen_button = QPushButton("Abbrechen", self)
        self.abbrechen_button.clicked.connect(self._abbrechen)
        self.schliessen_button = QPushButton("Schließen", self)
        self.schliessen_button.setEnabled(False)
        self.schliessen_button.clicked.connect(self.accept)
        aktionen.addWidget(self.abbrechen_button)
        aktionen.addWidget(self.schliessen_button)
        layout.addLayout(aktionen)

    def setze_abgeschlossen_callback(self, callback: AbgeschlossenCallback) -> None:
        self._abgeschlossen_callback = callback

    def _setze_aktuellen_befehl(
        self,
        argumente: list[str],
        label: str | None = None,
    ) -> None:
        self._befehl_nummer += 1
        if label is None:
            label = " ".join(shlex.quote(teil) for teil in ["podman", *argumente])
        self._aktueller_befehl_label = label
        self._aktueller_befehl_schluessel = f"befehl:{self._befehl_nummer}"
        self._parser.setze_befehl(
            argumente,
            self._aktueller_befehl_label,
            self._aktueller_befehl_schluessel,
        )
        self._setze_status_eintrag(
            ProzessStatusEintrag(
                schluessel=self._aktueller_befehl_schluessel,
                objekt=self._aktueller_befehl_label,
                typ="Befehl",
                zustand="Running",
            )
        )

    def _markiere_aktuellen_befehl(self, erfolgreich: bool, details: str = "") -> None:
        self._setze_status_eintrag(
            ProzessStatusEintrag(
                schluessel=self._aktueller_befehl_schluessel,
                objekt=self._aktueller_befehl_label,
                typ="Befehl",
                zustand="Done" if erfolgreich else "Error",
                details=details,
            )
        )

    def _haenge_ausgabe_an(self, text: str) -> None:
        if not text:
            return

        self._ausgabe.append(text)
        self._uebernehme_parser_ergebnis(self._parser.verarbeite(text))

    def _schliesse_ausgabe_ab(self) -> None:
        self._uebernehme_parser_ergebnis(self._parser.abschliessen())

    def _uebernehme_parser_ergebnis(self, ergebnis: ParserErgebnis) -> None:
        for eintrag in ergebnis.eintraege:
            self._setze_status_eintrag(eintrag)
        if ergebnis.resttext:
            self._haenge_rest_ausgabe_an(ergebnis.resttext)

    def _setze_status_eintrag(self, eintrag: ProzessStatusEintrag) -> None:
        zeile = self._status_zeilen.get(eintrag.schluessel)
        if zeile is None:
            zeile = self.status_tabelle.rowCount()
            self.status_tabelle.insertRow(zeile)
            self._status_zeilen[eintrag.schluessel] = zeile

        werte = [
            eintrag.objekt,
            eintrag.typ,
            eintrag.zustand,
            eintrag.fortschritt,
            eintrag.details,
        ]
        for spalte, wert in enumerate(werte):
            item = self.status_tabelle.item(zeile, spalte)
            if item is None:
                item = QTableWidgetItem()
                self.status_tabelle.setItem(zeile, spalte, item)
            item.setText(wert)

        self.status_tabelle.scrollToItem(
            self.status_tabelle.item(zeile, 0),
            QAbstractItemView.ScrollHint.EnsureVisible,
        )

    def _haenge_rest_ausgabe_an(self, text: str) -> None:
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)
        self.ausgabe_feld.insertPlainText(text)
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)

    def _abbrechen(self) -> None:
        raise NotImplementedError


class PodmanProzessDialog(_PodmanAusgabeDialogBasis):
    def __init__(
        self,
        titel: str,
        argumente: list[str],
        arbeitsverzeichnis: Path,
        umgebung: dict[str, str],
        *,
        timeout: int,
        prozess_name: str = "Podman Compose",
        parent=None,
    ):
        super().__init__(parent)
        self._argumente = argumente
        self._arbeitsverzeichnis = arbeitsverzeichnis
        self._umgebung = umgebung
        self._timeout = timeout
        self._prozess_name = prozess_name
        self._zeitlimit_erreicht = False
        self._abgeschlossen = False

        self._initialisiere_ausgabe_dialog(
            titel,
            f"{self._prozess_name} wird ausgeführt ...",
        )

        self._prozess = QProcess(self)
        self._prozess.setProgram("podman")
        self._prozess.setArguments(argumente)
        self._prozess.setWorkingDirectory(str(arbeitsverzeichnis))
        self._prozess.setProcessEnvironment(self._prozessumgebung())
        self._prozess.readyReadStandardOutput.connect(self._lese_stdout)
        self._prozess.readyReadStandardError.connect(self._lese_stderr)
        self._prozess.errorOccurred.connect(self._prozessfehler)
        self._prozess.finished.connect(self._prozess_beendet)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._zeitlimit_ueberschritten)

    def starten(self) -> None:
        befehl = " ".join(shlex.quote(teil) for teil in ["podman", *self._argumente])
        self._setze_aktuellen_befehl(self._argumente, befehl)
        self._haenge_ausgabe_an(f"$ {befehl}\n")
        self._prozess.start()
        self._timeout_timer.start(self._timeout * 1000)

    def _prozessumgebung(self) -> QProcessEnvironment:
        umgebung = QProcessEnvironment.systemEnvironment()
        for name, wert in self._umgebung.items():
            umgebung.insert(name, wert)
        return umgebung

    def _lese_stdout(self) -> None:
        self._haenge_ausgabe_an(
            bytes(self._prozess.readAllStandardOutput()).decode(errors="replace")
        )

    def _lese_stderr(self) -> None:
        self._haenge_ausgabe_an(
            bytes(self._prozess.readAllStandardError()).decode(errors="replace")
        )

    def _prozessfehler(self, fehler: QProcess.ProcessError) -> None:
        meldungen = _prozessfehler_meldungen()
        self._haenge_ausgabe_an(f"\n{meldungen.get(fehler, 'Podman-Prozessfehler.')}\n")
        if fehler == QProcess.ProcessError.FailedToStart:
            QTimer.singleShot(
                0,
                lambda: self._prozess_beendet(
                    -1,
                    QProcess.ExitStatus.CrashExit,
                ),
            )

    def _zeitlimit_ueberschritten(self) -> None:
        if self._prozess.state() == QProcess.ProcessState.NotRunning:
            return
        self._zeitlimit_erreicht = True
        self._haenge_ausgabe_an(
            f"\nZeitlimit von {self._timeout} Sekunden überschritten. Podman wird beendet.\n"
        )
        self._prozess.kill()

    def _abbrechen(self) -> None:
        if self._prozess.state() == QProcess.ProcessState.NotRunning:
            return
        self._haenge_ausgabe_an("\nVorgang wurde abgebrochen. Podman wird beendet.\n")
        self._prozess.kill()

    def closeEvent(self, event) -> None:
        if self._prozess.state() != QProcess.ProcessState.NotRunning:
            self._haenge_ausgabe_an(
                "\nDer Podman-Vorgang läuft noch. Bitte erst abbrechen oder das Ende abwarten.\n"
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _prozess_beendet(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._abgeschlossen:
            return
        self._abgeschlossen = True
        self._timeout_timer.stop()
        self._lese_stdout()
        self._lese_stderr()
        self._schliesse_ausgabe_ab()

        erfolgreich = (
            not self._zeitlimit_erreicht
            and exit_status == QProcess.ExitStatus.NormalExit
            and exit_code == 0
        )
        if erfolgreich:
            self.status_label.setText(f"{self._prozess_name} wurde erfolgreich beendet.")
        else:
            self.status_label.setText(
                f"{self._prozess_name} ist fehlgeschlagen. Exit-Code: {exit_code}"
            )

        self._markiere_aktuellen_befehl(
            erfolgreich,
            "" if erfolgreich else f"Exit-Code: {exit_code}",
        )
        self.abbrechen_button.setEnabled(False)
        self.schliessen_button.setEnabled(True)
        ausgabe = "".join(self._ausgabe).strip()
        if self._abgeschlossen_callback is not None:
            self._abgeschlossen_callback(erfolgreich, ausgabe)


class PodmanProzessKetteDialog(_PodmanAusgabeDialogBasis):
    def __init__(
        self,
        titel: str,
        befehle: list[tuple[str, list[str], dict[str, str]]],
        arbeitsverzeichnis: Path,
        *,
        timeout: int,
        parent=None,
    ):
        super().__init__(parent)
        self._befehle = befehle
        self._arbeitsverzeichnis = arbeitsverzeichnis
        self._timeout = timeout
        self._aktueller_index = -1
        self._zeitlimit_erreicht = False
        self._abgeschlossen = False

        self._initialisiere_ausgabe_dialog(
            titel,
            "Podman Compose wird ausgeführt ...",
        )

        self._prozess = QProcess(self)
        self._prozess.setProgram("podman")
        self._prozess.setWorkingDirectory(str(arbeitsverzeichnis))
        self._prozess.readyReadStandardOutput.connect(self._lese_stdout)
        self._prozess.readyReadStandardError.connect(self._lese_stderr)
        self._prozess.errorOccurred.connect(self._prozessfehler)
        self._prozess.finished.connect(self._prozess_beendet)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._zeitlimit_ueberschritten)

    def starten(self) -> None:
        self._starte_naechsten_befehl()

    def _starte_naechsten_befehl(self) -> None:
        self._aktueller_index += 1
        if self._aktueller_index >= len(self._befehle):
            self._beende_dialog(True, 0)
            return

        beschreibung, argumente, umgebung = self._befehle[self._aktueller_index]
        self.status_label.setText(beschreibung)
        self._setze_aktuellen_befehl(argumente, beschreibung)
        befehl = " ".join(shlex.quote(teil) for teil in ["podman", *argumente])
        self._haenge_ausgabe_an(f"\n## {beschreibung}\n$ {befehl}\n")
        self._prozess.setArguments(argumente)
        self._prozess.setProcessEnvironment(self._prozessumgebung(umgebung))
        self._prozess.start()
        self._timeout_timer.start(self._timeout * 1000)

    def _prozessumgebung(self, werte: dict[str, str]) -> QProcessEnvironment:
        umgebung = QProcessEnvironment.systemEnvironment()
        for name, wert in werte.items():
            umgebung.insert(name, wert)
        return umgebung

    def _lese_stdout(self) -> None:
        self._haenge_ausgabe_an(
            bytes(self._prozess.readAllStandardOutput()).decode(errors="replace")
        )

    def _lese_stderr(self) -> None:
        self._haenge_ausgabe_an(
            bytes(self._prozess.readAllStandardError()).decode(errors="replace")
        )

    def _prozessfehler(self, fehler: QProcess.ProcessError) -> None:
        meldungen = _prozessfehler_meldungen()
        self._haenge_ausgabe_an(f"\n{meldungen.get(fehler, 'Podman-Prozessfehler.')}\n")
        if fehler == QProcess.ProcessError.FailedToStart:
            self._markiere_aktuellen_befehl(False, "Podman konnte nicht gestartet werden.")
            QTimer.singleShot(0, lambda: self._beende_dialog(False, -1))

    def _zeitlimit_ueberschritten(self) -> None:
        if self._prozess.state() == QProcess.ProcessState.NotRunning:
            return
        self._zeitlimit_erreicht = True
        self._haenge_ausgabe_an(
            f"\nZeitlimit von {self._timeout} Sekunden überschritten. Podman wird beendet.\n"
        )
        self._prozess.kill()

    def _abbrechen(self) -> None:
        if self._prozess.state() == QProcess.ProcessState.NotRunning:
            return
        self._haenge_ausgabe_an("\nVorgang wurde abgebrochen. Podman wird beendet.\n")
        self._prozess.kill()

    def closeEvent(self, event) -> None:
        if self._prozess.state() != QProcess.ProcessState.NotRunning:
            self._haenge_ausgabe_an(
                "\nDer Podman-Vorgang läuft noch. Bitte erst abbrechen oder das Ende abwarten.\n"
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _prozess_beendet(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._timeout_timer.stop()
        self._lese_stdout()
        self._lese_stderr()
        self._schliesse_ausgabe_ab()
        if (
            self._zeitlimit_erreicht
            or exit_status != QProcess.ExitStatus.NormalExit
            or exit_code != 0
        ):
            self._markiere_aktuellen_befehl(False, f"Exit-Code: {exit_code}")
            self._beende_dialog(False, exit_code)
            return

        self._markiere_aktuellen_befehl(True)
        self._starte_naechsten_befehl()

    def _beende_dialog(self, erfolgreich: bool, exit_code: int) -> None:
        if self._abgeschlossen:
            return
        self._abgeschlossen = True
        self._timeout_timer.stop()
        if erfolgreich:
            self.status_label.setText("Podman Compose wurde erfolgreich beendet.")
        else:
            self.status_label.setText(
                f"Podman Compose ist fehlgeschlagen. Exit-Code: {exit_code}"
            )
        self.abbrechen_button.setEnabled(False)
        self.schliessen_button.setEnabled(True)
        ausgabe = "".join(self._ausgabe).strip()
        if self._abgeschlossen_callback is not None:
            self._abgeschlossen_callback(erfolgreich, ausgabe)


def _prozessfehler_meldungen() -> dict[QProcess.ProcessError, str]:
    return {
        QProcess.ProcessError.FailedToStart: "Podman konnte nicht gestartet werden.",
        QProcess.ProcessError.Crashed: "Podman wurde unerwartet beendet.",
        QProcess.ProcessError.Timedout: "Podman hat nicht rechtzeitig reagiert.",
        QProcess.ProcessError.ReadError: "Podman-Ausgabe konnte nicht gelesen werden.",
        QProcess.ProcessError.WriteError: "Podman-Eingabe konnte nicht geschrieben werden.",
        QProcess.ProcessError.UnknownError: "Unbekannter Podman-Prozessfehler.",
    }


def _bereinige_statuszeile(zeile: str) -> str:
    text = zeile.strip()
    text = re.sub(r"^\[\+\]\s*", "", text)
    text = re.sub(r"^[^\w./:-]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalisiere_zustand(zustand: str) -> str:
    for wort in _STATUS_WOERTER:
        if wort.lower() == zustand.lower():
            return wort
    return zustand


def _klassifiziere_objekt(objekt_roh: str) -> tuple[str, str]:
    teile = objekt_roh.split(maxsplit=1)
    if len(teile) == 2:
        prefix, rest = teile
        prefix_unten = prefix.lower()
        if prefix_unten == "container":
            return rest, "Container"
        if prefix_unten == "service":
            return rest, "Service"
        if prefix_unten == "image":
            return rest, "Image"
        if prefix_unten == "layer":
            return rest, "Layer"

    if "/" in objekt_roh or ":" in objekt_roh:
        return objekt_roh, "Image"

    return objekt_roh, "Service"


def _ist_image_layer(objekt: str) -> bool:
    if objekt.startswith("sha256:"):
        return True
    return bool(re.fullmatch(r"[a-fA-F0-9]{6,}", objekt))


def _extrahiere_fortschritt(text: str) -> str:
    treffer = _FORTSCHRITT_PATTERN.search(text)
    if treffer is None:
        return ""
    return treffer.group("prozent") or treffer.group("groesse") or ""
