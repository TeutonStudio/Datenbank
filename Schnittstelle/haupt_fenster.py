from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGridLayout, QMainWindow, QStackedWidget, QStatusBar, QWidget

from Schnittstelle.horizontale_leiste import HorizontaleLeiste
from Schnittstelle.vertikale_leiste import VertikaleLeiste
from Schnittstelle.verwaltung.verwaltung_fenster import VerwaltungFenster
from Schnittstelle.web_widget import ProgrammSeite

PROGRAMM_NAME = "N8N Verwalter"


class HauptFenster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1280, 800)

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("centralwidget")
        self.grid_layout = FensterLayout(self.central_widget)

        self.setCentralWidget(self.central_widget)
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.setWindowIcon(QIcon("./ui/icon/Logo.png"))
        self.setWindowTitle(PROGRAMM_NAME)

        self.grid_layout.init_list_widget()
        self.grid_layout.init_single_slot()
        self.grid_layout.wechsle_seite(0)

class FensterLayout(QGridLayout):
    def __init__(self, parent):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)
        self.setColumnStretch(1, 1)
        self.setRowStretch(1, 1)

        self.title_frame = HorizontaleLeiste(parent)
        self.addWidget(self.title_frame, 0, 0, 1, 2)

        # TODO PORT aus dem umgebungskontext auslesen
        PORT = "5678"

        self.navigationstitel = ["Verwaltung", "N8N"]

        self.stackedWidget = QStackedWidget(parent)
        self.stackedWidget.setObjectName("stackedWidget")
        self.stackedWidget.addWidget(VerwaltungFenster(self.stackedWidget))
        self.stackedWidget.addWidget(ProgrammSeite("http://localhost:"+PORT, self.stackedWidget))

        self.addWidget(self.stackedWidget, 1, 1, 1, 1)

        self.listWidget = VertikaleLeiste(
            parent=parent,
            liste=self.navigationstitel,
        )
        self.listWidget.setCurrentRow(0)
        self.addWidget(self.listWidget, 1, 0, 1, 1)

    def init_single_slot(self):
        self.title_frame.init_single_slot(self.listWidget, self.wechsle_seite)

    def init_list_widget(self):
        self.listWidget.neue_liste(self.navigationstitel)
        self.listWidget.setCurrentRow(0)

    def index_liste(self) -> range: return range(0,self.stackedWidget.count())
    def wechsle_seite(self, index: int) -> None:
        if index not in self.index_liste(): return
        self.stackedWidget.setCurrentIndex(index)
        self.title_frame.setze_titel(self.navigationstitel[index])
