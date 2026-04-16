import json
import shlex
import subprocess
from typing import Any

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout

from Kern.compose.env import Umgebungsvariablen
from Kern.podman import (
    PodmanComposeStartKonfiguration,
    PROJEKT_NAME,
    baue_startkonfiguration,
    lade_ausgewaehlte_dienste,
    lade_startkonfiguration,
    loesche_startkonfiguration,
    podman_compose_argumente,
    prozessumgebung_fuer_konfiguration,
    speichere_ausgewaehlte_dienste,
    speichere_startkonfiguration,
    startkonfigurationen_unterscheiden_sich,
)
from Schnittstelle.verwaltung.compose.ausgabe_widget import AusgabeBereich
from Schnittstelle.verwaltung.compose.container_widget import ContainerBereich, DienstDefinition
from Schnittstelle.verwaltung.compose.volumen_widget import VolumenBereich
from Schnittstelle.verwaltung.einstellungen_dialog import EinstellungenDialog

DIENSTE = [
    DienstDefinition("n8n", "N8N", ("n8n",), pflichtdienst=True),
    DienstDefinition("open-webui", "Open WebUI", ("open-webui",)),
    DienstDefinition("flowise", "Flowise", ("flowise",)),
    DienstDefinition("langfuse", "Langfuse", ("langfuse-web",)),
    DienstDefinition("neo4j", "Neo4j", ("neo4j",)),
    DienstDefinition("minio", "MinIO", ("minio",)),
    DienstDefinition("searxng", "SearXNG", ("searxng",)),
    DienstDefinition("supabase", "Supabase Studio", ("studio", "supabase-studio")),
    DienstDefinition("ollama", "Ollama", ("ollama", "ollama-cpu", "ollama-gpu", "ollama-gpu-amd")),
    DienstDefinition("immich", "Immich", ("immich-server",)),
]


class PodmanProzessDialog(QDialog):
    def __init__(
        self,
        titel: str,
        argumente: list[str],
        arbeitsverzeichnis,
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
        self._abgeschlossen_callback = None
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

    def setze_abgeschlossen_callback(self, callback) -> None:
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
        arbeitsverzeichnis,
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
        self._abgeschlossen_callback = None
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

    def setze_abgeschlossen_callback(self, callback) -> None:
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


# TODO vereinfachen
# TODO einen Selektor definieren, der übergreifend eines aus entweder container oder volumen auswählt (oder nichts). Dieser Selektor definiert welches log im ausgabe dargestellt wird (bei nichts ist es das des gesamten container)
# TODO Das Ausgabe widget braucht daher links von aktualisieren einen Knopf zum abwählen der aktuellen auswahl
# TODO da offenbar keine Volumenlog existent, beschränkt sich der Selektor auf container, die ausgabe ebenfalls
class ComposeWidget(QSplitter):
    def __init__(self, parent, umgebungsvariablen: Umgebungsvariablen):
        super().__init__(Qt.Orientation.Vertical,parent)
        self._projekt_pfad = parent.projekt_pfad
        self._umgebungsvariablen = umgebungsvariablen
        self._compose_status_pfad = self._projekt_pfad / ".compose.state.json"
        alter_status_pfad = self._projekt_pfad / "Schnittstelle" / ".compose.state.json"
        if not self._compose_status_pfad.exists() and alter_status_pfad.exists():
            self._compose_status_pfad = alter_status_pfad
        self._letzte_startkonfiguration = lade_startkonfiguration(
            self._compose_status_pfad
        )
        self._letzte_dienstauswahl = lade_ausgewaehlte_dienste(
            self._compose_status_pfad
        )
        self._container_status: dict[str, dict[str, object]] = {}
        self._ausgewaehlter_container: str | None = None
        self._ausgewaehlter_dienst = "Kein Dienst ausgewählt"
        self._letzter_status_fehler = ""
        self._start_dialog: PodmanProzessDialog | None = None
        self._prozess_dialoge: list[PodmanProzessDialog] = []

        self.container_bereich = ContainerBereich(DIENSTE, self)
        self.volumen_bereich = VolumenBereich(parent)
        self.ausgabe_bereich = AusgabeBereich(parent)

        if self._letzte_dienstauswahl is not None:
            self.container_bereich.setze_auswahl(
                self._letzte_dienstauswahl,
                als_manuelle_auswahl=True,
            )
            self._letzte_dienstauswahl = tuple(
                self.container_bereich.ausgewaehlte_dienst_ids()
            )
            speichere_ausgewaehlte_dienste(
                self._compose_status_pfad,
                self._letzte_dienstauswahl,
            )

        unterer_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        unterer_splitter.addWidget(self.volumen_bereich)
        unterer_splitter.addWidget(self.ausgabe_bereich)
        unterer_splitter.setStretchFactor(0, 1)
        unterer_splitter.setStretchFactor(1, 2)

        self.addWidget(self.container_bereich)
        self.addWidget(unterer_splitter)

        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 2)

        self.volumen_bereich.aktualisieren_angefragt.connect(self._aktualisiere_volumen)
        self.ausgabe_bereich.aktualisieren_angefragt.connect(self._aktualisiere_logs)

        self.container_bereich.container_gewaehlt.connect(self._setze_ausgewaehlten_container)
        self.container_bereich.dienste_schalten.connect(self._schalte_dienste)
        self.container_bereich.auswahl_geaendert.connect(self._bei_auswahl_geaendert)
        self.container_bereich.aktualisieren_angefragt.connect(self.aktualisiere_inhalt)
        self.container_bereich.einstellungen_angefragt.connect(self._oeffne_einstellungen)
        self.volumen_bereich.aktualisieren_angefragt.connect(self._aktualisiere_volumen)
        self.ausgabe_bereich.aktualisieren_angefragt.connect(self._aktualisiere_logs)

    def aktualisiere_inhalt(self) -> None:
        self._aktualisiere_container()
        self._aktualisiere_volumen()
        self._aktualisiere_logs()

    def _aktualisiere_container(self) -> None:
        container_rohdaten, fehler = self._lade_json_liste(["ps", "-a"])
        self._letzter_status_fehler = fehler
        self._container_status = self._status_nach_dienst(container_rohdaten)
        self._aktualisiere_containerdarstellung()

    def _aktualisiere_volumen(self) -> None:
        volumen_rohdaten, fehler = self._lade_json_liste(
            [
                "volume",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={PROJEKT_NAME}",
            ]
        )
        volumen_liste = []
        for volumen in volumen_rohdaten:
            volumen_liste.append(
                {
                    "name": str(volumen.get("Name") or ""),
                    "driver": str(volumen.get("Driver") or ""),
                    "mountpoint": str(volumen.get("Mountpoint") or ""),
                }
            )
        self.volumen_bereich.setze_volumen(volumen_liste, fehler)

    def _aktualisiere_logs(self) -> None:
        self.ausgabe_bereich.setze_ausgewaehlten_container(
            self._ausgewaehlter_container,
            self._ausgewaehlter_dienst,
        )

        if not self._ausgewaehlter_container:
            text = self._letzter_status_fehler or (
                "Für den ausgewählten Dienst wurde noch kein Podman-Container gefunden."
            )
            self.ausgabe_bereich.setze_ausgabe(text)
            return

        ausgabe, fehler = self._fuehre_podman_kommando(
            ["logs", "--tail", "200", self._ausgewaehlter_container]
        )
        if fehler:
            self.ausgabe_bereich.setze_ausgabe(fehler)
            return
        self.ausgabe_bereich.setze_ausgabe(ausgabe or "Keine Log-Ausgabe vorhanden.")

    def _setze_ausgewaehlten_container(
        self,
        container_name: str | None,
        dienst_titel: str,
    ) -> None:
        self._ausgewaehlter_container = container_name
        self._ausgewaehlter_dienst = dienst_titel
        self._aktualisiere_logs()

    def _schalte_dienste(self, befehl: str, dienst_ids: list[str]) -> None:
        if not dienst_ids:
            self.ausgabe_bereich.setze_ausgabe(
                "Keine passenden Dienste für diese Kollektiv-Aktion ausgewählt."
            )
            return

        if befehl == "start":
            self._starte_dienste(dienst_ids)
            return

        if befehl == "restart":
            self._neustarte_dienste(dienst_ids)
            return

        self._stoppe_dienste()

    def _bei_auswahl_geaendert(self) -> None:
        self._letzte_dienstauswahl = tuple(self.container_bereich.ausgewaehlte_dienst_ids())
        speichere_ausgewaehlte_dienste(
            self._compose_status_pfad,
            self._letzte_dienstauswahl,
        )
        self._aktualisiere_containerdarstellung()

    def _aktualisiere_containerdarstellung(self) -> None:
        self.container_bereich.setze_status(
            self._container_status,
            self._letzter_status_fehler,
            konfiguration_geaendert=self._konfiguration_ist_geaendert(),
        )

    def _konfiguration_ist_geaendert(self) -> bool:
        if not self._irgendetwas_laeuft():
            return False
        if self._letzte_startkonfiguration is None:
            return False

        aktuelle_konfiguration = self._gewuenschte_startkonfiguration()
        if aktuelle_konfiguration is None:
            return False

        return startkonfigurationen_unterscheiden_sich(
            aktuelle_konfiguration,
            self._letzte_startkonfiguration,
        )

    def _oeffne_einstellungen(self) -> None:
        dialog = EinstellungenDialog(
            self._umgebungsvariablen,
            self.container_bereich.ausgewaehlte_dienst_ids(),
            {dienst.dienst_id: dienst.titel for dienst in DIENSTE},
            self,
        )
        if dialog.exec():
            self.ausgabe_bereich.setze_ausgabe(
                f"Einstellungen gespeichert: {self._umgebungsvariablen.env_pfad.name}"
            )
            self._aktualisiere_containerdarstellung()

    def _lade_json_liste(self, basis_befehl: list[str]) -> tuple[list[dict[str, Any]], str]:
        daten, fehler = self._fuehre_podman_kommando([*basis_befehl, "--format", "json"])
        if daten:
            try:
                geparst = json.loads(daten)
                if isinstance(geparst, list):
                    return geparst, ""
                if isinstance(geparst, dict):
                    return [geparst], ""
            except json.JSONDecodeError:
                pass

        daten, fehler = self._fuehre_podman_kommando([*basis_befehl, "--format", "{{json .}}"])
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

    def _gewuenschte_startkonfiguration(
        self,
    ) -> PodmanComposeStartKonfiguration | None:
        try:
            return baue_startkonfiguration(
                self.container_bereich.ausgewaehlte_dienst_ids(),
                self._umgebungsvariablen,
            )
        except ValueError:
            return None

    def _irgendetwas_laeuft(self) -> bool:
        return any(
            bool(status.get("laeuft")) for status in self._container_status.values()
        )

    def _starte_dienste(self, dienst_ids: list[str]) -> None:
        if self._start_dialog is not None and self._start_dialog.isVisible():
            self._start_dialog.raise_()
            self._start_dialog.activateWindow()
            return

        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        argumente = podman_compose_argumente(
            startkonfiguration,
            "up",
            "-d",
            "--remove-orphans",
        )
        dialog = PodmanProzessDialog(
            "Compose-Stack starten",
            argumente,
            self._projekt_pfad,
            prozessumgebung_fuer_konfiguration(startkonfiguration),
            timeout=600,
            parent=self,
        )
        self._start_dialog = dialog
        self._prozess_dialoge.append(dialog)
        dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
        self.container_bereich.aktions_button.setEnabled(False)
        self.ausgabe_bereich.setze_ausgabe(
            f"Compose-Stack wird gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

        def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
            self.container_bereich.aktions_button.setEnabled(True)
            if self._start_dialog is dialog:
                self._start_dialog = None

            if not erfolgreich:
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack konnte nicht gestartet werden."
                )
                return

            speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
            self._letzte_startkonfiguration = startkonfiguration
            self.aktualisiere_inhalt()
            self.ausgabe_bereich.setze_ausgabe(
                ausgabe
                or f"Compose-Stack gestartet: {', '.join(startkonfiguration.dienst_ids)}"
            )

        dialog.setze_abgeschlossen_callback(abgeschlossen)
        dialog.starten()
        dialog.open()

    def _entferne_prozess_dialog(self, dialog: PodmanProzessDialog) -> None:
        if dialog in self._prozess_dialoge:
            self._prozess_dialoge.remove(dialog)

    def _neustarte_dienste(self, dienst_ids: list[str]) -> None:
        if self._start_dialog is not None and self._start_dialog.isVisible():
            self._start_dialog.raise_()
            self._start_dialog.activateWindow()
            return

        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        stopp_konfiguration = self._letzte_startkonfiguration or startkonfiguration
        dialog = PodmanProzessKetteDialog(
            "Compose-Stack neu starten",
            [
                (
                    "Compose-Stack wird gestoppt ...",
                    podman_compose_argumente(
                        stopp_konfiguration,
                        "down",
                        "--remove-orphans",
                    ),
                    prozessumgebung_fuer_konfiguration(stopp_konfiguration),
                ),
                (
                    "Compose-Stack wird neu gestartet ...",
                    podman_compose_argumente(
                        startkonfiguration,
                        "up",
                        "-d",
                        "--remove-orphans",
                        "--force-recreate",
                    ),
                    prozessumgebung_fuer_konfiguration(startkonfiguration),
                ),
            ],
            self._projekt_pfad,
            timeout=600,
            parent=self,
        )
        self._start_dialog = dialog
        self._prozess_dialoge.append(dialog)
        dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
        self.container_bereich.aktions_button.setEnabled(False)
        self.ausgabe_bereich.setze_ausgabe(
            f"Compose-Stack wird neu gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

        def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
            self.container_bereich.aktions_button.setEnabled(True)
            if self._start_dialog is dialog:
                self._start_dialog = None

            if not erfolgreich:
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack konnte nicht neu gestartet werden."
                )
                return

            speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
            self._letzte_startkonfiguration = startkonfiguration
            self.aktualisiere_inhalt()
            self.ausgabe_bereich.setze_ausgabe(
                ausgabe
                or f"Compose-Stack neu gestartet: {', '.join(startkonfiguration.dienst_ids)}"
            )

        dialog.setze_abgeschlossen_callback(abgeschlossen)
        dialog.starten()
        dialog.open()

    def _stoppe_dienste(self) -> None:
        if self._letzte_startkonfiguration is not None:
            if self._start_dialog is not None and self._start_dialog.isVisible():
                self._start_dialog.raise_()
                self._start_dialog.activateWindow()
                return

            startkonfiguration = self._letzte_startkonfiguration
            dialog = PodmanProzessDialog(
                "Compose-Stack stoppen",
                podman_compose_argumente(
                    startkonfiguration,
                    "down",
                    "--remove-orphans",
                ),
                self._projekt_pfad,
                prozessumgebung_fuer_konfiguration(startkonfiguration),
                timeout=300,
                parent=self,
            )
            self._start_dialog = dialog
            self._prozess_dialoge.append(dialog)
            dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
            self.container_bereich.aktions_button.setEnabled(False)
            self.ausgabe_bereich.setze_ausgabe(
                f"Compose-Stack wird gestoppt: {', '.join(startkonfiguration.dienst_ids)}"
            )

            def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
                self.container_bereich.aktions_button.setEnabled(True)
                if self._start_dialog is dialog:
                    self._start_dialog = None

                if not erfolgreich:
                    self.ausgabe_bereich.setze_ausgabe(
                        ausgabe or "Compose-Stack konnte nicht gestoppt werden."
                    )
                    return

                loesche_startkonfiguration(self._compose_status_pfad)
                self._letzte_startkonfiguration = None
                self.aktualisiere_inhalt()
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack gestoppt und entfernt."
                )

            dialog.setze_abgeschlossen_callback(abgeschlossen)
            dialog.starten()
            dialog.open()
            return

        bearbeitet, fehler_liste = self._stoppe_bekannte_container()
        self.aktualisiere_inhalt()

        if fehler_liste:
            self.ausgabe_bereich.setze_ausgabe("\n\n".join(fehler_liste))
            return

        if bearbeitet:
            self.ausgabe_bereich.setze_ausgabe(
                f"stop: {', '.join(bearbeitet)}"
            )
            return

        self.ausgabe_bereich.setze_ausgabe(
            "Es wurden keine laufenden Container gefunden."
        )

    def _stoppe_bekannte_container(
        self,
        *,
        entfernen: bool = False,
    ) -> tuple[list[str], list[str]]:
        bearbeitet: list[str] = []
        fehler_liste: list[str] = []
        befehl = "rm" if entfernen else "stop"

        for dienst in DIENSTE:
            status = self._container_status.get(dienst.dienst_id, {})
            container_name = str(status.get("container_name") or "")
            if not container_name:
                continue
            if not entfernen and not bool(status.get("laeuft")):
                continue

            argumente = [befehl, container_name]
            if entfernen:
                argumente.insert(1, "-f")

            _, fehler = self._fuehre_podman_kommando(argumente, timeout=120)
            if fehler:
                fehler_liste.append(f"{container_name}: {fehler}")
                continue
            bearbeitet.append(container_name)

        return bearbeitet, fehler_liste

    def _status_nach_dienst(
        self,
        container_rohdaten: list[dict[str, Any]],
    ) -> dict[str, dict[str, object]]:
        container_index: dict[str, dict[str, Any]] = {}
        for container in container_rohdaten:
            for name in self._container_namen(container):
                container_index[name.lower()] = container

        status_nach_dienst: dict[str, dict[str, object]] = {}
        for dienst in DIENSTE:
            container = self._finde_container_fuer_dienst(dienst, container_index)
            status_nach_dienst[dienst.dienst_id] = self._formatierter_status(container)
        return status_nach_dienst

    def _finde_container_fuer_dienst(
        self,
        dienst: DienstDefinition,
        container_index: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        for kandidat in dienst.container_namen:
            kandidat_lower = kandidat.lower()
            if kandidat_lower in container_index:
                return container_index[kandidat_lower]

            for container_name, container in container_index.items():
                if container_name.startswith(f"{kandidat_lower}-"):
                    return container

        return None

    def _formatierter_status(self, container: dict[str, Any] | None) -> dict[str, object]:
        if not container:
            return {
                "container_name": None,
                "laeuft": False,
                "anzeige_status": "Nicht gefunden",
            }

        state = str(container.get("State") or "").lower()
        status = str(container.get("Status") or container.get("State") or "Unbekannt")
        return {
            "container_name": self._container_namen(container)[0] if self._container_namen(container) else None,
            "laeuft": state == "running" or status.lower().startswith("up"),
            "anzeige_status": status,
        }

    def _container_namen(self, container: dict[str, Any]) -> list[str]:
        namen = container.get("Names") or container.get("Name") or []
        if isinstance(namen, str):
            return [namen]
        if isinstance(namen, list):
            return [str(name) for name in namen if name]
        return []

    def _fuehre_podman_kommando(
        self,
        argumente: list[str],
        *,
        umgebung: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> tuple[str, str]:
        try:
            ergebnis = subprocess.run(
                ["podman", *argumente],
                cwd=self._projekt_pfad,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=umgebung,
            )
        except FileNotFoundError:
            return "", "Podman wurde nicht gefunden. Installation und Runtime folgen im nächsten Schritt."
        except subprocess.TimeoutExpired:
            return "", "Die Podman-Abfrage hat das Zeitlimit überschritten."

        stdout = ergebnis.stdout.strip()
        stderr = ergebnis.stderr.strip()
        if ergebnis.returncode != 0:
            return "", stderr or stdout or "Die Podman-Abfrage ist fehlgeschlagen."
        return stdout, ""
