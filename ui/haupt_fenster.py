from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGridLayout, QMainWindow, QStackedWidget, QStatusBar, QWidget

from ui.horizontale_leiste import HorizontaleLeiste
from ui.vertikale_leiste import VertikaleLeiste
from ui.verwaltung_fenster import VerwaltungFenster
from ui.web_fenster import ProgrammSeite

PROGRAMM_NAME = "N8N Verwalter"


class HauptFenster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1280, 800)
        self.navigationstitel = ["Verwaltung", "N8N"]

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("centralwidget")
        self.grid_layout = QGridLayout(self.central_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(0)
        self.grid_layout.setColumnStretch(1, 1)
        self.grid_layout.setRowStretch(1, 1)

        self.title_frame = HorizontaleLeiste(self.central_widget)
        self.grid_layout.addWidget(self.title_frame, 0, 0, 1, 2)

        self.stackedWidget = QStackedWidget(self.central_widget)
        self.stackedWidget.setObjectName("stackedWidget")
        self.stackedWidget.addWidget(VerwaltungFenster(self.stackedWidget))
        self.stackedWidget.addWidget(ProgrammSeite("http://localhost:5678", self.stackedWidget))
        self.grid_layout.addWidget(self.stackedWidget, 1, 1, 1, 1)

        self.listWidget = VertikaleLeiste(
            parent=self.central_widget,
            liste=self.navigationstitel,
        )
        self.grid_layout.addWidget(self.listWidget, 1, 0, 1, 1)

        self.setCentralWidget(self.central_widget)
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.setWindowIcon(QIcon("./ui/icon/Logo.png"))
        self.setWindowTitle(PROGRAMM_NAME)

        self.side_menu = self.listWidget
        self.main_content = self.stackedWidget

        self.init_list_widget()
        self.init_single_slot()
        self.wechsle_seite(0)

    def init_single_slot(self):
        self.title_frame.init_single_slot(self.side_menu, self.wechsle_seite)

    def init_list_widget(self):
        self.side_menu.neue_liste(self.navigationstitel)
        self.side_menu.setCurrentRow(0)

    def wechsle_seite(self, index: int) -> None:
        if index < 0 or index >= self.main_content.count():
            return
        self.main_content.setCurrentIndex(index)
        self.title_frame.setze_titel(self.navigationstitel[index])
