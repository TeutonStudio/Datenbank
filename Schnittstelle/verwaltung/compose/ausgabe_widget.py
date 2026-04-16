from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AusgabeBereich(QGroupBox):
    aktualisieren_angefragt = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Ausgabe", parent)
        self._container_name: str | None = None
        self._dienst_titel = "Kein Dienst ausgewählt"

        layout = QVBoxLayout(self)
        kopfzeile = QHBoxLayout()
        self.auswahl_label = QLabel("Kein Dienst ausgewählt", self)
        self.auswahl_label.setWordWrap(True)
        self.aktualisieren_button = QPushButton("Aktualisieren", self)
        self.aktualisieren_button.clicked.connect(self.aktualisieren_angefragt.emit)
        kopfzeile.addWidget(self.auswahl_label)
        kopfzeile.addStretch()
        kopfzeile.addWidget(self.aktualisieren_button)
        layout.addLayout(kopfzeile)

        self.textfeld = QPlainTextEdit(self)
        self.textfeld.setReadOnly(True)
        self.textfeld.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.textfeld.setMaximumBlockCount(1000)
        self.textfeld.setPlaceholderText(
            "Die Logs des ausgewählten Containers werden hier angezeigt."
        )
        layout.addWidget(self.textfeld)

    def setze_ausgewaehlten_container(
        self,
        container_name: str | None,
        dienst_titel: str,
    ) -> None:
        self._container_name = container_name
        self._dienst_titel = dienst_titel
        if container_name:
            self.auswahl_label.setText(f"{dienst_titel}: {container_name}")
            return
        self.auswahl_label.setText(f"{dienst_titel}: kein Container gefunden")

    def setze_ausgabe(self, text: str) -> None:
        self.textfeld.setPlainText(text)

    @property
    def container_name(self) -> str | None:
        return self._container_name
