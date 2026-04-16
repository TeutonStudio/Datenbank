from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


AbgeschlossenCallback = Callable[[bool, str], None]


class PodmanProzessDialog(QDialog):
    def __init__(
        self,
        titel: str,
        argumente: list[str],
        arbeitsverzeichnis: Path,
        umgebung: dict[str, str],
        *,
        timeout: int,
        parent=None,
    ):
        super().__init__(parent)
        self._argumente = argumente
        self._arbeitsverzeichnis = arbeitsverzeichnis
        self._umgebung = umgebung
        self._timeout = timeout
        self._ausgabe: list[str] = []
        self._abgeschlossen_callback: AbgeschlossenCallback | None = None
        self._zeitlimit_erreicht = False
        self._abgeschlossen = False

        self.setWindowTitle(titel)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Podman Compose wird ausgeführt ...", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.ausgabe_feld = QPlainTextEdit(self)
        self.ausgabe_feld.setReadOnly(True)
        self.ausgabe_feld.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.ausgabe_feld)

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

    def setze_abgeschlossen_callback(self, callback: AbgeschlossenCallback) -> None:
        self._abgeschlossen_callback = callback

    def starten(self) -> None:
        befehl = " ".join(shlex.quote(teil) for teil in ["podman", *self._argumente])
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

    def _haenge_ausgabe_an(self, text: str) -> None:
        if not text:
            return
        self._ausgabe.append(text)
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)
        self.ausgabe_feld.insertPlainText(text)
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)

    def _prozessfehler(self, fehler: QProcess.ProcessError) -> None:
        meldungen = {
            QProcess.ProcessError.FailedToStart: "Podman konnte nicht gestartet werden.",
            QProcess.ProcessError.Crashed: "Podman wurde unerwartet beendet.",
            QProcess.ProcessError.Timedout: "Podman hat nicht rechtzeitig reagiert.",
            QProcess.ProcessError.ReadError: "Podman-Ausgabe konnte nicht gelesen werden.",
            QProcess.ProcessError.WriteError: "Podman-Eingabe konnte nicht geschrieben werden.",
            QProcess.ProcessError.UnknownError: "Unbekannter Podman-Prozessfehler.",
        }
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

        erfolgreich = (
            not self._zeitlimit_erreicht
            and exit_status == QProcess.ExitStatus.NormalExit
            and exit_code == 0
        )
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


class PodmanProzessKetteDialog(QDialog):
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
        self._ausgabe: list[str] = []
        self._abgeschlossen_callback: AbgeschlossenCallback | None = None
        self._zeitlimit_erreicht = False
        self._abgeschlossen = False

        self.setWindowTitle(titel)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Podman Compose wird ausgeführt ...", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.ausgabe_feld = QPlainTextEdit(self)
        self.ausgabe_feld.setReadOnly(True)
        self.ausgabe_feld.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.ausgabe_feld)

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

    def setze_abgeschlossen_callback(self, callback: AbgeschlossenCallback) -> None:
        self._abgeschlossen_callback = callback

    def starten(self) -> None:
        self._starte_naechsten_befehl()

    def _starte_naechsten_befehl(self) -> None:
        self._aktueller_index += 1
        if self._aktueller_index >= len(self._befehle):
            self._beende_dialog(True, 0)
            return

        beschreibung, argumente, umgebung = self._befehle[self._aktueller_index]
        self.status_label.setText(beschreibung)
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

    def _haenge_ausgabe_an(self, text: str) -> None:
        if not text:
            return
        self._ausgabe.append(text)
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)
        self.ausgabe_feld.insertPlainText(text)
        self.ausgabe_feld.moveCursor(QTextCursor.MoveOperation.End)

    def _prozessfehler(self, fehler: QProcess.ProcessError) -> None:
        meldungen = {
            QProcess.ProcessError.FailedToStart: "Podman konnte nicht gestartet werden.",
            QProcess.ProcessError.Crashed: "Podman wurde unerwartet beendet.",
            QProcess.ProcessError.Timedout: "Podman hat nicht rechtzeitig reagiert.",
            QProcess.ProcessError.ReadError: "Podman-Ausgabe konnte nicht gelesen werden.",
            QProcess.ProcessError.WriteError: "Podman-Eingabe konnte nicht geschrieben werden.",
            QProcess.ProcessError.UnknownError: "Unbekannter Podman-Prozessfehler.",
        }
        self._haenge_ausgabe_an(f"\n{meldungen.get(fehler, 'Podman-Prozessfehler.')}\n")
        if fehler == QProcess.ProcessError.FailedToStart:
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
        if (
            self._zeitlimit_erreicht
            or exit_status != QProcess.ExitStatus.NormalExit
            or exit_code != 0
        ):
            self._beende_dialog(False, exit_code)
            return

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
