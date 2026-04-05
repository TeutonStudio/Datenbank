from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, QModelIndex
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

class Tabelle(QTableWidget):
    def __init__(self, start: int, parent = None, header_labels: dict[str,QHeaderView.ResizeMode] = {}):
        super().__init__(start, len(header_labels), parent)
        
        self.setHorizontalHeaderLabels(header_labels.keys())
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        
        v_header = self.verticalHeader()
        h_header = self.horizontalHeader()
        
        if v_header: v_header.setVisible(False)
        if h_header:
            for i,mode in enumerate(header_labels.values()):
                h_header.setSectionResizeMode(i,mode)
        # self.tabelle.currentCellChanged.connect(self._sende_aktuelle_auswahl)
    
    def selektierte_zeile(self) -> int:
        model = self.selectionModel()
        reihen = model.selectedRows() if model else []
        return reihen[0].row() if reihen else -1
        