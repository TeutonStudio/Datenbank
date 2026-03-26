from __future__ import annotations

import json
from pathlib import Path

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

from compose.podman import ComposeVariable


class EinstellungenDialog(QDialog):
    def __init__(
        self,
        env_pfad: Path,
        cache_pfad: Path,
        ausgewaehlte_dienste: list[str],
        dienst_titel: dict[str, str],
        dienst_variablen: dict[str, tuple[ComposeVariable, ...]],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._env_pfad = env_pfad
        self._cache_pfad = cache_pfad
        self._dienst_titel = dienst_titel
        self._ausgewaehlte_dienste = [
            dienst_id for dienst_id in ausgewaehlte_dienste if dienst_id in dienst_titel
        ]
        self._dienst_variablen = dienst_variablen
        self._tabellen_update_laeuft = False
        self._variablen_meta = self._baue_variablen_meta()

        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.resize(980, 520)

        layout = QVBoxLayout(self)

        pfad_label = QLabel(
            f".env-Datei: {self._env_pfad}",
            self,
        )
        pfad_label.setWordWrap(True)
        layout.addWidget(pfad_label)

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

# TODO Umgebungsvariablen als eigene Klasse
    def _baue_variablen_meta(self) -> dict[str, dict[str, object]]:
        meta_nach_name: dict[str, dict[str, object]] = {}
        for dienst_id in self._ausgewaehlte_dienste:
            for variable in self._dienst_variablen.get(dienst_id, ()):
                eintrag = meta_nach_name.setdefault(
                    variable.name,
                    {
                        "dienst_ids": [],
                        "hat_standardwert": False,
                        "standardwert": None,
                    },
                )
                if dienst_id not in eintrag["dienst_ids"] :
                    eintrag["dienst_ids"].append(dienst_id)
                eintrag["hat_standardwert"] = (
                    bool(eintrag["hat_standardwert"]) or variable.hat_standardwert
                )
                if eintrag["standardwert"] is None and variable.standardwert is not None:
                    eintrag["standardwert"] = variable.standardwert
        return meta_nach_name

    def _lade_startdaten(self) -> None:
        zeilen = self._lade_entwurf() or self._lade_env_datei()
        vorhandene_variablen = {name for name, _wert in zeilen if name}

        for variable in self._variablen_meta:
            if variable not in vorhandene_variablen:
                zeilen.append((variable, ""))

        if not zeilen:
            zeilen.append(("", ""))

        self._tabellen_update_laeuft = True
        try:
            self.tabelle.setRowCount(0)
            for variable, wert in zeilen:
                self._fuege_zeile_hinzu(variable, wert, speichere_entwurf=False)
            self._aktualisiere_alle_zeilen()
        finally:
            self._tabellen_update_laeuft = False

    def _lade_entwurf(self) -> list[tuple[str, str]]:
        if not self._cache_pfad.exists():
            return []

        try:
            daten = json.loads(self._cache_pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        if not isinstance(daten, list):
            return []

        zeilen: list[tuple[str, str]] = []
        for eintrag in daten:
            if not isinstance(eintrag, dict):
                continue
            variable = str(eintrag.get("variable") or "").strip()
            wert = str(eintrag.get("wert") or "")
            zeilen.append((variable, wert))
        return zeilen

    def _lade_env_datei(self) -> list[tuple[str, str]]:
        eintraege: list[tuple[str, str]] = []
        if self._env_pfad.exists():
            for zeile in self._env_pfad.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#") or "=" not in zeile:
                    continue
                schluessel, wert = zeile.split("=", 1)
                schluessel = schluessel.strip()
                if not schluessel:
                    continue
                eintraege.append((schluessel, wert))
        return eintraege

    def _fuege_zeile_hinzu(
        self,
        schluessel: str = "",
        wert: str = "",
        *,
        speichere_entwurf: bool = True,
    ) -> None:
        zeile = self.tabelle.rowCount()
        self.tabelle.insertRow(zeile)

        dienst_item = QTableWidgetItem("")
        dienst_item.setFlags(dienst_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        schluessel_item = QTableWidgetItem(schluessel)
        schluessel_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        wert_item = QTableWidgetItem(wert)
        wert_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        status_item = QTableWidgetItem("")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self.tabelle.setItem(zeile, 0, dienst_item)
        self.tabelle.setItem(zeile, 1, schluessel_item)
        self.tabelle.setItem(zeile, 2, wert_item)
        self.tabelle.setItem(zeile, 3, status_item)

        if not schluessel and not wert:
            self.tabelle.setCurrentCell(zeile, 1)
            self.tabelle.editItem(schluessel_item)

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

    def _aktualisiere_zeile(self, zeile: int) -> None:
        variable_item = self.tabelle.item(zeile, 1)
        wert_item = self.tabelle.item(zeile, 2)
        dienst_item = self.tabelle.item(zeile, 0)
        status_item = self.tabelle.item(zeile, 3)
        if (
            variable_item is None
            or wert_item is None
            or dienst_item is None
            or status_item is None
        ):
            return

        variable = variable_item.text().strip()
        wert = wert_item.text()
        meta = self._variablen_meta.get(variable)

        if not variable:
            dienst_text = "Manuell"
            status_text = "Neu"
            variable_item.setFlags(variable_item.flags() | Qt.ItemFlag.ItemIsEditable)
        elif meta:
            dienste = ", ".join(
                self._dienst_titel[dienst_id]
                for dienst_id in meta["dienst_ids"]
                if dienst_id in self._dienst_titel
            )
            dienst_text = dienste
            if wert.strip():
                status_text = "Definiert"
            elif bool(meta["hat_standardwert"]):
                status_text = "Compose-Standard"
            else:
                status_text = "Fehlt"
            variable_item.setFlags(variable_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        else:
            dienst_text = "Manuell"
            status_text = "Zusätzlich" if wert.strip() else "Leer"
            variable_item.setFlags(variable_item.flags() | Qt.ItemFlag.ItemIsEditable)

        dienst_item.setText(dienst_text)
        status_item.setText(status_text)

    def _speichere_entwurf(self) -> None:
        zeilen = []
        for zeile in range(self.tabelle.rowCount()):
            variable_item = self.tabelle.item(zeile, 1)
            wert_item = self.tabelle.item(zeile, 2)
            variable = (variable_item.text() if variable_item else "").strip()
            wert = wert_item.text() if wert_item else ""
            if not variable and not wert:
                continue
            zeilen.append({"variable": variable, "wert": wert})

        if not zeilen:
            if self._cache_pfad.exists():
                self._cache_pfad.unlink()
            return

        self._cache_pfad.write_text(
            json.dumps(zeilen, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def _sammle_eintraege(self) -> list[tuple[str, str]] | None:
        eintraege: list[tuple[str, str]] = []
        bekannte_schluessel: set[str] = set()

        for zeile in range(self.tabelle.rowCount()):
            schluessel_item = self.tabelle.item(zeile, 1)
            wert_item = self.tabelle.item(zeile, 2)
            schluessel = (schluessel_item.text() if schluessel_item else "").strip()
            wert = wert_item.text() if wert_item else ""

            if not schluessel and not wert:
                continue

            if not schluessel:
                QMessageBox.warning(
                    self,
                    "Ungültige Variable",
                    f"Zeile {zeile + 1} enthält einen Wert ohne Variablennamen.",
                )
                return None

            if schluessel in bekannte_schluessel:
                QMessageBox.warning(
                    self,
                    "Doppelte Variable",
                    f"Die Variable '{schluessel}' ist mehrfach vorhanden.",
                )
                return None

            bekannte_schluessel.add(schluessel)
            eintraege.append((schluessel, wert))

        return eintraege

    def _speichere_und_schliesse(self) -> None:
        eintraege = self._sammle_eintraege()
        if eintraege is None:
            return

        inhalt = "\n".join(f"{schluessel}={wert}" for schluessel, wert in eintraege)
        if inhalt:
            inhalt = f"{inhalt}\n"

        self._env_pfad.write_text(inhalt, encoding="utf-8")
        if self._cache_pfad.exists():
            self._cache_pfad.unlink()
        self.accept()
