from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class VolumenBereich(QGroupBox):
    aktualisieren_angefragt = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Volumen", parent)

        layout = QVBoxLayout(self)
        kopfzeile = QHBoxLayout()
        self.hinweis_label = QLabel("", self)
        self.hinweis_label.setWordWrap(True)
        self.aktualisieren_button = QPushButton("Aktualisieren", self)
        self.aktualisieren_button.clicked.connect(self.aktualisieren_angefragt.emit)
        kopfzeile.addWidget(self.hinweis_label)
        kopfzeile.addStretch()
        kopfzeile.addWidget(self.aktualisieren_button)
        layout.addLayout(kopfzeile)

        self.tabelle = QTableWidget(0, 3, self)
        self.tabelle.setHorizontalHeaderLabels(["Name", "Treiber", "Mountpoint"])
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setAlternatingRowColors(True)
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tabelle)

    def setze_volumen(
        self,
        volumen_liste: list[dict[str, str]],
        hinweis: str = "",
    ) -> None:
        self.hinweis_label.setText(hinweis)
        self.tabelle.setRowCount(max(1, len(volumen_liste)))

        if not volumen_liste:
            self.tabelle.setItem(0, 0, QTableWidgetItem("Keine Podman-Volumen gefunden"))
            self.tabelle.setItem(0, 1, QTableWidgetItem(""))
            self.tabelle.setItem(0, 2, QTableWidgetItem(""))
            return

        for zeile, volumen in enumerate(volumen_liste):
            self.tabelle.setItem(zeile, 0, QTableWidgetItem(volumen.get("name", "")))
            self.tabelle.setItem(zeile, 1, QTableWidgetItem(volumen.get("driver", "")))
            self.tabelle.setItem(zeile, 2, QTableWidgetItem(volumen.get("mountpoint", "")))
