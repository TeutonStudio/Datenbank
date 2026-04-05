from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from Kern.compose.env import Umgebungsvariablen, Umgebungsvariable


class EinstellungenDialog(QDialog):
    def __init__(
        self,
        env_verwaltung: Umgebungsvariablen,
        ausgewaehlte_dienste: list[str],
        dienst_titel: dict[str, str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._env_verwaltung = env_verwaltung
        self._dienst_titel = dienst_titel
        self._ausgewaehlte_dienste = [
            dienst_id for dienst_id in ausgewaehlte_dienste if dienst_id in dienst_titel
        ]
        self._tabellen_update_laeuft = False
        self._definitionen_nach_name = self._env_verwaltung.definitionen_fuer_dienste(
            self._ausgewaehlte_dienste
        )

        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.resize(980, 520)

        layout = QVBoxLayout(self)

        self.pfad_label = QLabel(
            f".env-Datei: {self._env_verwaltung.env_pfad}",
            self,
        )
        self.pfad_label.setWordWrap(True)
        layout.addWidget(self.pfad_label)

        dienste_text = ", ".join(
            self._dienst_titel[dienst_id] for dienst_id in self._ausgewaehlte_dienste
        )
        self.auswahl_label = QLabel(
            f"Ausgewählte Dienste: {dienste_text or 'keine optionalen Dienste aktiv'}",
            self,
        )
        self.auswahl_label.setWordWrap(True)
        layout.addWidget(self.auswahl_label)

        self.hinweis_label = QLabel(
            "Fehlende Compose-Variablen der aktuellen Auswahl werden automatisch als neue Zeilen ergänzt. "
            "Nicht gespeicherte Änderungen bleiben als Entwurf zwischengespeichert.",
            self,
        )
        self.hinweis_label.setWordWrap(True)
        layout.addWidget(self.hinweis_label)

        tabellen_aktionen = QHBoxLayout()
        self.hinzufuegen_button = QPushButton("Zeile hinzufügen", self)
        self.hinzufuegen_button.clicked.connect(lambda: self._fuege_zeile_hinzu())
        self.entfernen_button = QPushButton("Zeile entfernen", self)
        self.entfernen_button.clicked.connect(self._entferne_ausgewaehlte_zeile)
        tabellen_aktionen.addWidget(self.hinzufuegen_button)
        tabellen_aktionen.addWidget(self.entfernen_button)
        tabellen_aktionen.addStretch()
        layout.addLayout(tabellen_aktionen)

        self.tabelle = QTableWidget(0, 4, self)
        self.tabelle.setHorizontalHeaderLabels(["Dienst", "Variable", "Wert", "Status"])
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabelle.setAlternatingRowColors(True)
        vHeader = self.tabelle.verticalHeader()
        hHeader = self.tabelle.horizontalHeader()
        if vHeader: vHeader.setVisible(False)
        if hHeader:
            hHeader.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hHeader.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hHeader.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hHeader.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tabelle)

        dialog_aktionen = QHBoxLayout()
        dialog_aktionen.addStretch()
        self.speichern_button = QPushButton("Speichern", self)
        self.speichern_button.clicked.connect(self._speichere_und_schliesse)
        self.abbrechen_button = QPushButton("Abbrechen", self)
        self.abbrechen_button.clicked.connect(self.reject)
        dialog_aktionen.addWidget(self.speichern_button)
        dialog_aktionen.addWidget(self.abbrechen_button)
        layout.addLayout(dialog_aktionen)

        self.tabelle.itemChanged.connect(self._verarbeite_tabellen_aenderung)

        self._lade_startdaten()

    def _lade_startdaten(self) -> None:
        variablen = self._env_verwaltung.variablen_fuer_dienste(
            self._ausgewaehlte_dienste,
            entwurf_bevorzugen=True,
        )
        if not variablen:
            variablen = [Umgebungsvariable(name="", wert="")]

        self._tabellen_update_laeuft = True
        try:
            self.tabelle.setRowCount(0)
            for variable in variablen:
                self._fuege_zeile_hinzu(variable, speichere_entwurf=False)
            self._aktualisiere_alle_zeilen()
        finally:
            self._tabellen_update_laeuft = False

    def _fuege_zeile_hinzu(
        self,
        variable: Umgebungsvariable | None = None,
        *,
        speichere_entwurf: bool = True,
    ) -> None:
        if variable is None:
            variable = Umgebungsvariable(name="", wert="")

        zeile = self.tabelle.rowCount()
        self.tabelle.insertRow(zeile)

        dienst_item = QTableWidgetItem("")
        dienst_item.setFlags(dienst_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        name_item = QTableWidgetItem(variable.name)
        name_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        wert_item = QTableWidgetItem(variable.wert)
        wert_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        status_item = QTableWidgetItem("")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self.tabelle.setItem(zeile, 0, dienst_item)
        self.tabelle.setItem(zeile, 1, name_item)
        self.tabelle.setItem(zeile, 2, wert_item)
        self.tabelle.setItem(zeile, 3, status_item)

        if not variable.name and not variable.wert:
            self.tabelle.setCurrentCell(zeile, 1)
            self.tabelle.editItem(name_item)

        if speichere_entwurf:
            self._aktualisiere_alle_zeilen()
            self._speichere_entwurf()

    def _entferne_ausgewaehlte_zeile(self) -> None:
        aktuelle_zeile = self.tabelle.currentRow()
        if aktuelle_zeile >= 0:
            self.tabelle.removeRow(aktuelle_zeile)

        if self.tabelle.rowCount() == 0:
            self._fuege_zeile_hinzu(speichere_entwurf=False)

        self._aktualisiere_alle_zeilen()
        self._speichere_entwurf()

    def _verarbeite_tabellen_aenderung(self, _item: QTableWidgetItem) -> None:
        if self._tabellen_update_laeuft:
            return
        self._aktualisiere_alle_zeilen()
        self._speichere_entwurf()

    def _aktualisiere_alle_zeilen(self) -> None:
        self._tabellen_update_laeuft = True
        try:
            for zeile in range(self.tabelle.rowCount()):
                self._aktualisiere_zeile(zeile)
        finally:
            self._tabellen_update_laeuft = False

    def _lese_variable_aus_zeile(self, zeile: int) -> Umgebungsvariable:
        name_item = self.tabelle.item(zeile, 1)
        wert_item = self.tabelle.item(zeile, 2)
        name = (name_item.text() if name_item else "").strip()
        wert = wert_item.text() if wert_item else ""

        definition = self._definitionen_nach_name.get(name)
        if definition is None:
            return Umgebungsvariable(name=name, wert=wert)

        return Umgebungsvariable(
            name=name,
            wert=wert,
            dienst_ids=definition.dienst_ids,
            hat_standardwert=definition.hat_standardwert,
            standardwert=definition.standardwert,
            dateien=definition.dateien,
        )

    def _aktualisiere_zeile(self, zeile: int) -> None:
        variable = self._lese_variable_aus_zeile(zeile)
        dienst_item = self.tabelle.item(zeile, 0)
        name_item = self.tabelle.item(zeile, 1)
        status_item = self.tabelle.item(zeile, 3)
        if dienst_item is None or name_item is None or status_item is None:
            return

        if not variable.name:
            dienst_item.setText("Manuell")
            status_item.setText("Neu")
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
            return

        if variable.ist_manuell:
            dienst_item.setText("Manuell")
            status_item.setText("Zusätzlich" if variable.ist_definiert else "Leer")
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
            return

        dienste_text = ", ".join(
            self._dienst_titel[dienst_id]
            for dienst_id in variable.dienst_ids
            if dienst_id in self._dienst_titel
        )
        dienst_item.setText(dienste_text)
        if variable.ist_definiert:
            status_item.setText("Definiert")
        elif variable.hat_standardwert:
            status_item.setText("Compose-Standard")
        else:
            status_item.setText("Fehlt")
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _tabellen_variablen(self) -> list[Umgebungsvariable]:
        variablen = []
        for zeile in range(self.tabelle.rowCount()):
            variable = self._lese_variable_aus_zeile(zeile)
            if not variable.name and not variable.wert:
                continue
            variablen.append(variable)
        return variablen

    def _speichere_entwurf(self) -> None:
        self._env_verwaltung.speichere_entwurf(self._tabellen_variablen())

    def _sammle_eintraege(self) -> list[Umgebungsvariable] | None:
        eintraege = self._tabellen_variablen()
        bekannte_schluessel: set[str] = set()

        for zeile, variable in enumerate(eintraege, start=1):
            if not variable.name:
                QMessageBox.warning(
                    self,
                    "Ungültige Variable",
                    f"Zeile {zeile} enthält einen Wert ohne Variablennamen.",
                )
                return None

            if variable.name in bekannte_schluessel:
                QMessageBox.warning(
                    self,
                    "Doppelte Variable",
                    f"Die Variable '{variable.name}' ist mehrfach vorhanden.",
                )
                return None

            bekannte_schluessel.add(variable.name)

        return eintraege

    def _speichere_und_schliesse(self) -> None:
        eintraege = self._sammle_eintraege()
        if eintraege is None:
            return

        self._env_verwaltung.speichere_env(eintraege)
        self.accept()
