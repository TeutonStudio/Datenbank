from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.verwaltung.tabelle import Tabelle


@dataclass(frozen=True)
class DienstDefinition:
    dienst_id: str
    titel: str
    container_namen: tuple[str, ...]
    pflichtdienst: bool = False


class ContainerBereich(QGroupBox):
    container_gewaehlt = pyqtSignal(object, str)
    dienste_schalten = pyqtSignal(str, list)
    aktualisieren_angefragt = pyqtSignal()
    einstellungen_angefragt = pyqtSignal()
    auswahl_geaendert = pyqtSignal()

    def __init__(self, dienste: list[DienstDefinition], parent: QWidget | None = None):
        super().__init__("Container", parent)
        self._dienste = dienste
        self._auswahl = {dienst.dienst_id: dienst.pflichtdienst for dienst in dienste}
        self._manuelle_auswahl: set[str] = set()
        self._status_nach_dienst: dict[str, dict[str, object]] = {}
        self._checkboxen: dict[str, QCheckBox] = {}
        self._titel_nach_dienst = {dienst.dienst_id: dienst.titel for dienst in dienste}
        self._konfiguration_geaendert = False

        layout = QVBoxLayout(self)
        kopfzeile = QHBoxLayout()
        self.einstellungen_button = QPushButton("Einstellungen", self)
        self.einstellungen_button.clicked.connect(
            lambda: self.einstellungen_angefragt.emit()
        )
        self.aktualisieren_button = QPushButton("Aktualisieren", self)
        self.aktualisieren_button.clicked.connect(self.aktualisieren_angefragt.emit)
        self.aktions_button = QPushButton("Start", self)
        self.aktions_button.clicked.connect(self._sende_kollektivaktion)
        kopfzeile.addWidget(self.einstellungen_button)
        kopfzeile.addStretch()
        kopfzeile.addWidget(self.aktualisieren_button)
        kopfzeile.addWidget(self.aktions_button)
        layout.addLayout(kopfzeile)

        self.tabelle = Tabelle(len(dienste),self,{
            "Dienst": QHeaderView.ResizeMode.Stretch, 
            "Aktiv": QHeaderView.ResizeMode.ResizeToContents, 
            "Container": QHeaderView.ResizeMode.Stretch, 
            "Status": QHeaderView.ResizeMode.ResizeToContents,
        })
        # QTableWidget(len(dienste), 4, self)
        # self.tabelle.setHorizontalHeaderLabels(["Dienst", "Aktiv", "Container", "Status"])
        # self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # self.tabelle.verticalHeader().setVisible(False)
        # self.tabelle.setAlternatingRowColors(True)
        # self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        # self.tabelle.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # self.tabelle.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabelle.currentCellChanged.connect(self._sende_aktuelle_auswahl)
        layout.addWidget(self.tabelle)

        self._baue_zeilen()
        self._aktualisiere_aktionsbuttons()

    def _baue_zeilen(self) -> None:
        for zeile, dienst in enumerate(self._dienste):
            dienst_item = QTableWidgetItem(dienst.titel)
            dienst_item.setData(Qt.ItemDataRole.UserRole, dienst.dienst_id)
            self.tabelle.setItem(zeile, 0, dienst_item)

            checkbox = QCheckBox(self)
            checkbox.setChecked(self._auswahl[dienst.dienst_id])
            checkbox.setEnabled(not dienst.pflichtdienst)
            checkbox.stateChanged.connect(
                partial(self._setze_auswahlstatus, dienst.dienst_id)
            )
            checkbox_widget = QWidget(self)
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.tabelle.setCellWidget(zeile, 1, checkbox_widget)
            self._checkboxen[dienst.dienst_id] = checkbox

            self.tabelle.setItem(zeile, 2, QTableWidgetItem("-"))
            self.tabelle.setItem(zeile, 3, QTableWidgetItem("Unbekannt"))

        if self.tabelle.rowCount():
            self.tabelle.selectRow(0)

    def _setze_auswahlstatus(self, dienst_id: str, status: int) -> None:
        self._manuelle_auswahl.add(dienst_id)
        self._auswahl[dienst_id] = status == Qt.CheckState.Checked.value
        self._aktualisiere_zeile(dienst_id)
        self._aktualisiere_aktionsbuttons()
        self.auswahl_geaendert.emit()

    def _sende_kollektivaktion(self) -> None:
        befehl = self._ermittle_kollektivaktion()
        dienste = self.ausgewaehlte_dienst_ids()
        if dienste:
            self.dienste_schalten.emit(befehl, dienste)

    def ausgewaehlte_dienst_ids(self) -> list[str]:
        return [
            dienst.dienst_id
            for dienst in self._dienste
            if self._auswahl.get(dienst.dienst_id, False)
        ]

    def _zeile_fuer_dienst(self, dienst_id: str) -> int:
        for zeile in range(self.tabelle.rowCount()):
            item = self.tabelle.item(zeile, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == dienst_id:
                return zeile
        return -1

    def _aktualisiere_zeile(self, dienst_id: str) -> None:
        zeile = self._zeile_fuer_dienst(dienst_id)
        if zeile < 0:
            return

        status = self._status_nach_dienst.get(dienst_id, {})
        container_name = str(status.get("container_name") or "-")
        status_text = str(status.get("anzeige_status") or "Unbekannt")

        container_item = self.tabelle.item(zeile, 2)
        if container_item is not None:
            container_item.setText(container_name)

        status_item = self.tabelle.item(zeile, 3)
        if status_item is not None:
            status_item.setText(status_text)

    def setze_status(
        self,
        status_nach_dienst: dict[str, dict[str, object]],
        podman_hinweis: str = "",
        konfiguration_geaendert: bool = False,
    ) -> None:
        self._status_nach_dienst = status_nach_dienst
        self._konfiguration_geaendert = konfiguration_geaendert

        for dienst in self._dienste:
            status = status_nach_dienst.get(dienst.dienst_id, {})
            if (
                dienst.dienst_id not in self._manuelle_auswahl
                and not dienst.pflichtdienst
                and bool(status.get("container_name"))
            ):
                self._auswahl[dienst.dienst_id] = True
                checkbox = self._checkboxen[dienst.dienst_id]
                vorher = checkbox.blockSignals(True)
                checkbox.setChecked(True)
                checkbox.blockSignals(vorher)

            if podman_hinweis and not bool(status.get("container_name")):
                status = dict(status)
                status["anzeige_status"] = podman_hinweis
                self._status_nach_dienst[dienst.dienst_id] = status

            self._aktualisiere_zeile(dienst.dienst_id)

        self._aktualisiere_aktionsbuttons()
        self._sende_aktuelle_auswahl()

    def _irgendetwas_laeuft(self) -> bool:
        return any(
            bool(status.get("laeuft")) for status in self._status_nach_dienst.values()
        )

    def _ermittle_kollektivaktion(self) -> str:
        if not self._irgendetwas_laeuft():
            return "start"
        if self._konfiguration_geaendert:
            return "restart"
        return "stop"

    def _aktualisiere_aktionsbuttons(self) -> None:
        befehl = self._ermittle_kollektivaktion()
        texte = {
            "start": "Start",
            "stop": "Stop",
            "restart": "Neustart",
        }
        self.aktions_button.setText(texte[befehl])
        self.aktions_button.setEnabled(bool(self.ausgewaehlte_dienst_ids()))

    def _sende_aktuelle_auswahl(self, aktuelle_zeile: int | None = None, *_args) -> None:
        zeile = aktuelle_zeile
        if zeile is None or zeile < 0: zeile = self.tabelle.selektierteZeile()
        if zeile < 0:
            self.container_gewaehlt.emit(None, "Kein Dienst ausgewählt")
            return

        item = self.tabelle.item(zeile, 0)
        if item is None:
            self.container_gewaehlt.emit(None, "Kein Dienst ausgewählt")
            return

        dienst_id = str(item.data(Qt.ItemDataRole.UserRole))
        status = self._status_nach_dienst.get(dienst_id, {})
        self.container_gewaehlt.emit(
            status.get("container_name"),
            self._titel_nach_dienst[dienst_id],
        )
