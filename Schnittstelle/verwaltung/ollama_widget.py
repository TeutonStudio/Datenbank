from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from Schnittstelle.consolen_dialog import PodmanProzessDialog
from Schnittstelle.verwaltung.tabelle_widget import Tabelle


@dataclass(frozen=True)
class OllamaModell:
    name: str
    modell_id: str
    groesse: str
    geaendert: str


class OllamaWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._projekt_pfad = Path(__file__).resolve().parents[2]
        self._pull_dialog: PodmanProzessDialog | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        kopfzeile = QHBoxLayout()
        self.pull_button = QPushButton("Pull", self)
        self.pull_button.clicked.connect(self._starte_pull)
        kopfzeile.addWidget(self.pull_button)

        self.modell_eingabe = QLineEdit(self)
        self.modell_eingabe.setPlaceholderText("Modellname, z. B. llama3.2")
        self.modell_eingabe.returnPressed.connect(self._starte_pull)
        kopfzeile.addWidget(self.modell_eingabe, 1)
        layout.addLayout(kopfzeile)

        self.status_label = QLabel("Modelle werden geladen ...", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.tabelle = Tabelle(
            0,
            self,
            {
                "Modell": QHeaderView.ResizeMode.Stretch,
                "ID": QHeaderView.ResizeMode.ResizeToContents,
                "Größe": QHeaderView.ResizeMode.ResizeToContents,
                "Geändert": QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        layout.addWidget(self.tabelle, 1)

        self.aktualisierungs_timer = QTimer(self)
        self.aktualisierungs_timer.setInterval(5000)
        self.aktualisierungs_timer.timeout.connect(self.aktualisiere_modelle)
        self.aktualisierungs_timer.start()

        self.aktualisiere_modelle()

    def aktualisiere_modelle(self) -> None:
        ausgabe, fehler = self._fuehre_podman_kommando(
            ["exec", "ollama", "ollama", "list"],
            timeout=10,
        )
        if fehler:
            self._setze_modelle([])
            self.status_label.setText(fehler)
            return

        modelle = self._parse_ollama_list(ausgabe)
        self._setze_modelle(modelle)
        if modelle:
            self.status_label.setText(f"{len(modelle)} Modell(e) im Ollama-Container.")
        else:
            self.status_label.setText("Keine Modelle im Ollama-Container gefunden.")

    def _starte_pull(self) -> None:
        modellname = self.modell_eingabe.text().strip()
        if not modellname:
            self.status_label.setText("Bitte einen Modellnamen für den Pull eingeben.")
            self.modell_eingabe.setFocus()
            return

        if self._pull_dialog is not None and self._pull_dialog.isVisible():
            self._pull_dialog.raise_()
            self._pull_dialog.activateWindow()
            return

        dialog = PodmanProzessDialog(
            f"Ollama-Modell pull: {modellname}",
            ["exec", "ollama", "ollama", "pull", modellname],
            self._projekt_pfad,
            {},
            timeout=3600,
            prozess_name="Ollama Pull",
            parent=self,
        )
        self._pull_dialog = dialog
        self.pull_button.setEnabled(False)
        self.status_label.setText(f"Pull läuft: {modellname}")

        def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
            self.pull_button.setEnabled(True)
            if self._pull_dialog is dialog:
                self._pull_dialog = None
            if erfolgreich:
                self.status_label.setText(f"Pull abgeschlossen: {modellname}")
            else:
                self.status_label.setText(
                    ausgabe or f"Pull fehlgeschlagen: {modellname}"
                )
            self.aktualisiere_modelle()

        dialog.finished.connect(lambda _result: self._dialog_beendet(dialog))
        dialog.setze_abgeschlossen_callback(abgeschlossen)
        dialog.starten()
        dialog.open()

    def _dialog_beendet(self, dialog: PodmanProzessDialog) -> None:
        if self._pull_dialog is dialog:
            self._pull_dialog = None
            self.pull_button.setEnabled(True)

    def _setze_modelle(self, modelle: list[OllamaModell]) -> None:
        self.tabelle.setRowCount(len(modelle))
        for zeile, modell in enumerate(modelle):
            self.tabelle.setItem(zeile, 0, QTableWidgetItem(modell.name))
            self.tabelle.setItem(zeile, 1, QTableWidgetItem(modell.modell_id))
            self.tabelle.setItem(zeile, 2, QTableWidgetItem(modell.groesse))
            self.tabelle.setItem(zeile, 3, QTableWidgetItem(modell.geaendert))

    def _parse_ollama_list(self, ausgabe: str) -> list[OllamaModell]:
        modelle: list[OllamaModell] = []
        for zeile in ausgabe.splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("NAME"):
                continue

            spalten = zeile.split()
            if len(spalten) < 4:
                continue

            name = spalten[0]
            modell_id = spalten[1]
            groesse = " ".join(spalten[2:4])
            geaendert = " ".join(spalten[4:]) if len(spalten) > 4 else "-"
            modelle.append(
                OllamaModell(
                    name=name,
                    modell_id=modell_id,
                    groesse=groesse,
                    geaendert=geaendert,
                )
            )
        return modelle

    def _fuehre_podman_kommando(
        self,
        argumente: list[str],
        *,
        timeout: int,
    ) -> tuple[str, str]:
        try:
            ergebnis = subprocess.run(
                ["podman", *argumente],
                cwd=self._projekt_pfad,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError:
            return "", "Podman wurde nicht gefunden."
        except subprocess.TimeoutExpired:
            return "", "Die Ollama-Abfrage hat das Zeitlimit überschritten."
        except KeyboardInterrupt:
            return "", "Die Ollama-Abfrage wurde abgebrochen."

        stdout = ergebnis.stdout.strip()
        stderr = ergebnis.stderr.strip()
        if ergebnis.returncode != 0:
            return "", stderr or stdout or "Die Ollama-Abfrage ist fehlgeschlagen."
        return stdout, ""
