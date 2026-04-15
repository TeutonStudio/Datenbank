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
    _DIENST_SPALTE = 0
    _NAME_SPALTE = 1
    _WERT_SPALTE = 2
    _STATUS_SPALTE = 3
    _ZEILENTYP_ROLLE = Qt.ItemDataRole.UserRole
    _GRUPPEN_SCHLUESSEL_ROLLE = Qt.ItemDataRole.UserRole.value + 1
    _GRUPPEN_TITEL_ROLLE = Qt.ItemDataRole.UserRole.value + 2
    _GRUPPEN_ANZAHL_ROLLE = Qt.ItemDataRole.UserRole.value + 3
    _ZEILENTYP_GRUPPE = "gruppe"
    _ZEILENTYP_VARIABLE = "variable"

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
        self._gruppen_eingeklappt: dict[str, bool] = {}
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
        self.tabelle.setShowGrid(False)
        self.tabelle.setStyleSheet(
            "QTableWidget { gridline-color: transparent; }"
            "QTableWidget::item { border: 0px; }"
        )
        vHeader = self.tabelle.verticalHeader()
        hHeader = self.tabelle.horizontalHeader()
        if vHeader:
            vHeader.setVisible(True)
            vHeader.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            vHeader.setSectionsClickable(True)
            vHeader.sectionPressed.connect(self._verarbeite_zeilenkopf_klick)
        if hHeader:
            hHeader.setSectionResizeMode(self._DIENST_SPALTE, QHeaderView.ResizeMode.ResizeToContents)
            hHeader.setSectionResizeMode(self._NAME_SPALTE, QHeaderView.ResizeMode.ResizeToContents)
            hHeader.setSectionResizeMode(self._WERT_SPALTE, QHeaderView.ResizeMode.Stretch)
            hHeader.setSectionResizeMode(self._STATUS_SPALTE, QHeaderView.ResizeMode.ResizeToContents)
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
        self.tabelle.cellClicked.connect(self._verarbeite_tabellen_klick)

        self._lade_startdaten()

    def _lade_startdaten(self) -> None:
        variablen = self._env_verwaltung.variablen_fuer_dienste(
            self._ausgewaehlte_dienste,
            entwurf_bevorzugen=True,
        )
        if not variablen:
            variablen = [Umgebungsvariable(name="", wert="")]

        self._setze_variablen(variablen)

    def _fuege_zeile_hinzu(
        self,
        variable: Umgebungsvariable | None = None,
        *,
        speichere_entwurf: bool = True,
    ) -> None:
        if variable is None:
            variable = Umgebungsvariable(name="", wert="")

        variablen = self._tabellen_variablen()
        variablen.append(variable)
        ziel_index = len(variablen) - 1
        gruppen_schluessel, _gruppen_titel = self._gruppeninfo(variable)
        self._gruppen_eingeklappt[gruppen_schluessel] = False
        self._setze_variablen(
            variablen,
            aktive_variable_index=ziel_index,
            name_bearbeiten=not variable.name,
        )

        if speichere_entwurf:
            self._speichere_entwurf()

    def _setze_variablen(
        self,
        variablen: list[Umgebungsvariable],
        *,
        aktive_variable_index: int | None = None,
        name_bearbeiten: bool = False,
    ) -> None:
        self._tabellen_update_laeuft = True
        ziel_zeile = -1
        ziel_name_item: QTableWidgetItem | None = None
        try:
            self.tabelle.setRowCount(0)

            gruppen: dict[str, tuple[str, list[Umgebungsvariable]]] = {}
            for variable in variablen:
                gruppen_schluessel, gruppen_titel = self._gruppeninfo(variable)
                if gruppen_schluessel not in gruppen:
                    gruppen[gruppen_schluessel] = (gruppen_titel, [])
                gruppen[gruppen_schluessel][1].append(variable)

            variable_index = 0
            for gruppen_schluessel, (gruppen_titel, gruppen_variablen) in gruppen.items():
                eingeklappt = self._gruppen_eingeklappt.get(gruppen_schluessel, False)
                self._fuege_gruppenzeile_hinzu(
                    gruppen_schluessel,
                    gruppen_titel,
                    len(gruppen_variablen),
                    eingeklappt=eingeklappt,
                )

                variable_index_in_gruppe = 0
                for gruppen_variable in gruppen_variablen:
                    zeile = self._fuege_variablenzeile_hinzu(
                        gruppen_schluessel,
                        gruppen_variable,
                        nummer_in_gruppe=variable_index_in_gruppe + 1,
                    )
                    self.tabelle.setRowHidden(zeile, eingeklappt)
                    if variable_index == aktive_variable_index:
                        ziel_zeile = zeile
                        ziel_name_item = self.tabelle.item(zeile, self._NAME_SPALTE)
                    variable_index += 1
                    variable_index_in_gruppe += 1
        finally:
            self._tabellen_update_laeuft = False

        if ziel_zeile >= 0:
            self.tabelle.selectRow(ziel_zeile)
            if name_bearbeiten and ziel_name_item is not None:
                self.tabelle.setCurrentCell(ziel_zeile, self._NAME_SPALTE)
                self.tabelle.editItem(ziel_name_item)

    def _fuege_gruppenzeile_hinzu(
        self,
        gruppen_schluessel: str,
        gruppen_titel: str,
        anzahl: int,
        *,
        eingeklappt: bool,
    ) -> None:
        zeile = self.tabelle.rowCount()
        self.tabelle.insertRow(zeile)

        gruppen_item = QTableWidgetItem(
            self._gruppenzeilen_text(gruppen_titel, anzahl, eingeklappt)
        )
        gruppen_item.setData(self._ZEILENTYP_ROLLE, self._ZEILENTYP_GRUPPE)
        gruppen_item.setData(self._GRUPPEN_SCHLUESSEL_ROLLE, gruppen_schluessel)
        gruppen_item.setData(self._GRUPPEN_TITEL_ROLLE, gruppen_titel)
        gruppen_item.setData(self._GRUPPEN_ANZAHL_ROLLE, anzahl)
        gruppen_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        schrift = gruppen_item.font()
        schrift.setBold(True)
        gruppen_item.setFont(schrift)
        self.tabelle.setItem(zeile, self._DIENST_SPALTE, gruppen_item)
        self.tabelle.setVerticalHeaderItem(
            zeile,
            QTableWidgetItem("+" if eingeklappt else "-"),
        )
        self.tabelle.setSpan(zeile, self._DIENST_SPALTE, 1, 4)

    def _fuege_variablenzeile_hinzu(
        self,
        gruppen_schluessel: str,
        variable: Umgebungsvariable,
        *,
        nummer_in_gruppe: int,
    ) -> int:
        zeile = self.tabelle.rowCount()
        self.tabelle.insertRow(zeile)

        dienst_item = QTableWidgetItem("")
        dienst_item.setData(self._ZEILENTYP_ROLLE, self._ZEILENTYP_VARIABLE)
        dienst_item.setData(self._GRUPPEN_SCHLUESSEL_ROLLE, gruppen_schluessel)
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

        self.tabelle.setItem(zeile, self._DIENST_SPALTE, dienst_item)
        self.tabelle.setItem(zeile, self._NAME_SPALTE, name_item)
        self.tabelle.setItem(zeile, self._WERT_SPALTE, wert_item)
        self.tabelle.setItem(zeile, self._STATUS_SPALTE, status_item)
        self.tabelle.setVerticalHeaderItem(
            zeile,
            QTableWidgetItem(str(nummer_in_gruppe)),
        )

        self._aktualisiere_zeile(zeile)
        return zeile

    def _entferne_ausgewaehlte_zeile(self) -> None:
        aktuelle_zeile = self.tabelle.currentRow()
        if not self._ist_variablenzeile(aktuelle_zeile):
            return

        aktuelle_variable = self._variablen_index_fuer_zeile(aktuelle_zeile)
        variablen = self._tabellen_variablen()
        if aktuelle_variable is not None:
            del variablen[aktuelle_variable]

        if not variablen:
            variablen = [Umgebungsvariable(name="", wert="")]

        ziel_index = min(aktuelle_variable or 0, len(variablen) - 1)
        self._setze_variablen(variablen, aktive_variable_index=ziel_index)
        self._speichere_entwurf()

    def _verarbeite_tabellen_aenderung(self, _item: QTableWidgetItem) -> None:
        if self._tabellen_update_laeuft:
            return
        zeile = _item.row()
        if not self._ist_variablenzeile(zeile):
            return

        aktive_variable_index = self._variablen_index_fuer_zeile(zeile)
        self._setze_variablen(
            self._tabellen_variablen(),
            aktive_variable_index=aktive_variable_index,
        )
        self._speichere_entwurf()

    def _verarbeite_tabellen_klick(self, zeile: int, _spalte: int) -> None:
        if not self._ist_gruppenzeile(zeile):
            return
        gruppen_item = self.tabelle.item(zeile, self._DIENST_SPALTE)
        if gruppen_item is None:
            return
        gruppen_schluessel = str(
            gruppen_item.data(self._GRUPPEN_SCHLUESSEL_ROLLE) or ""
        )
        if not gruppen_schluessel:
            return
        self._setze_gruppe_eingeklappt(
            zeile,
            gruppen_schluessel,
            not self._gruppen_eingeklappt.get(gruppen_schluessel, False),
        )

    def _verarbeite_zeilenkopf_klick(self, zeile: int) -> None:
        self._verarbeite_tabellen_klick(zeile, self._DIENST_SPALTE)

    def _setze_gruppe_eingeklappt(
        self,
        gruppen_zeile: int,
        gruppen_schluessel: str,
        eingeklappt: bool,
    ) -> None:
        self._gruppen_eingeklappt[gruppen_schluessel] = eingeklappt
        gruppen_item = self.tabelle.item(gruppen_zeile, self._DIENST_SPALTE)
        if gruppen_item is not None:
            titel, anzahl = self._gruppenzeilen_daten(gruppen_zeile)
            gruppen_item.setText(
                self._gruppenzeilen_text(titel, anzahl, eingeklappt)
            )
        self.tabelle.setVerticalHeaderItem(
            gruppen_zeile,
            QTableWidgetItem("+" if eingeklappt else "-"),
        )

        for zeile in range(gruppen_zeile + 1, self.tabelle.rowCount()):
            if self._ist_gruppenzeile(zeile):
                break
            self.tabelle.setRowHidden(zeile, eingeklappt)

    def _aktualisiere_alle_zeilen(self) -> None:
        self._tabellen_update_laeuft = True
        try:
            for zeile in self._variablenzeilen():
                self._aktualisiere_zeile(zeile)
        finally:
            self._tabellen_update_laeuft = False

    def _gruppeninfo(self, variable: Umgebungsvariable) -> tuple[str, str]:
        if not variable.name or variable.ist_manuell:
            return "manuell", "Manuell"

        dienst_ids = tuple(
            dienst_id
            for dienst_id in variable.dienst_ids
            if dienst_id in self._dienst_titel
        )
        if not dienst_ids:
            return "dienst:unbekannt", "Dienst"

        titel = ", ".join(self._dienst_titel[dienst_id] for dienst_id in dienst_ids)
        return f"dienst:{'|'.join(dienst_ids)}", titel

    def _gruppenzeilen_text(
        self,
        titel: str,
        anzahl: int,
        eingeklappt: bool,
    ) -> str:
        einheit = "Variable" if anzahl == 1 else "Variablen"
        return f"{titel} ({anzahl} {einheit})"

    def _gruppenzeilen_daten(self, zeile: int) -> tuple[str, int]:
        gruppen_item = self.tabelle.item(zeile, self._DIENST_SPALTE)
        if gruppen_item is None:
            return "", 0
        titel = str(gruppen_item.data(self._GRUPPEN_TITEL_ROLLE) or "")
        anzahl = gruppen_item.data(self._GRUPPEN_ANZAHL_ROLLE)
        return titel, int(anzahl) if isinstance(anzahl, int) else 0

    def _ist_gruppenzeile(self, zeile: int) -> bool:
        if zeile < 0:
            return False
        item = self.tabelle.item(zeile, self._DIENST_SPALTE)
        return bool(
            item is not None
            and item.data(self._ZEILENTYP_ROLLE) == self._ZEILENTYP_GRUPPE
        )

    def _ist_variablenzeile(self, zeile: int) -> bool:
        if zeile < 0:
            return False
        item = self.tabelle.item(zeile, self._DIENST_SPALTE)
        return bool(
            item is not None
            and item.data(self._ZEILENTYP_ROLLE) == self._ZEILENTYP_VARIABLE
        )

    def _variablenzeilen(self) -> list[int]:
        return [
            zeile
            for zeile in range(self.tabelle.rowCount())
            if self._ist_variablenzeile(zeile)
        ]

    def _variablen_index_fuer_zeile(self, ziel_zeile: int) -> int | None:
        index = 0
        for zeile in range(self.tabelle.rowCount()):
            if not self._ist_variablenzeile(zeile):
                continue
            if zeile == ziel_zeile:
                return index
            index += 1
        return None

    def _lese_variable_aus_zeile(self, zeile: int) -> Umgebungsvariable:
        name_item = self.tabelle.item(zeile, self._NAME_SPALTE)
        wert_item = self.tabelle.item(zeile, self._WERT_SPALTE)
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
        dienst_item = self.tabelle.item(zeile, self._DIENST_SPALTE)
        name_item = self.tabelle.item(zeile, self._NAME_SPALTE)
        status_item = self.tabelle.item(zeile, self._STATUS_SPALTE)
        if dienst_item is None or name_item is None or status_item is None:
            return

        dienst_item.setText("")
        if not variable.name:
            status_item.setText("Neu")
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
            return

        if variable.ist_manuell:
            status_item.setText("Zusätzlich" if variable.ist_definiert else "Leer")
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
            return

        if variable.ist_definiert:
            status_item.setText("Definiert")
        elif variable.hat_standardwert:
            status_item.setText("Compose-Standard")
        else:
            status_item.setText("Fehlt")
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _tabellen_variablen(self) -> list[Umgebungsvariable]:
        variablen = []
        for zeile in self._variablenzeilen():
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
