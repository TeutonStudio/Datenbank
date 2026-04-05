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
    def __init__(self,start: int, parent = None, headerLabels: dict[str,QHeaderView.ResizeMode] = {}):
        super().__init__(start,len(headerLabels),parent)
        
        self.setHorizontalHeaderLabels(headerLabels.keys())
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        
        vHeader = self.verticalHeader()
        hHeader = self.horizontalHeader()
        
        if vHeader: vHeader.setVisible(False)
        if hHeader: 
            for i,mode in enumerate(headerLabels.values()):
                hHeader.setSectionResizeMode(i,mode)
        # self.tabelle.currentCellChanged.connect(self._sende_aktuelle_auswahl)
    
    def selektierteZeile(self) -> int:
        model = self.selectionModel()
        reihen = model.selectedRows() if model else []
        return reihen[0].row() if reihen else -1
        