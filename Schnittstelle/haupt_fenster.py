from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGridLayout, QMainWindow, QStackedWidget, QStatusBar, QWidget

from Schnittstelle.horizontale_leiste import HorizontaleLeiste
from Schnittstelle.vertikale_leiste import VertikaleLeiste
from Schnittstelle.verwaltung.ollama_widget import OllamaWidget
from Schnittstelle.verwaltung.verwaltung_fenster import VerwaltungFenster
from Schnittstelle.verwaltung.web_widget import ProgrammSeite

PROGRAMM_NAME = "Selatrix"
PROGRAMM_SEITEN = [
    ("Verwaltung", None),
    ("N8N", "http://localhost:5678"),
    ("Open WebUI", "http://localhost:8080"),
    ("Flowise", "http://localhost:3001"),
    ("Langfuse", "http://localhost:3000"),
    ("SearXNG", "http://localhost:8081"),
    ("Neo4j", "http://localhost:7474"),
    ("MinIO", "http://localhost:9011"),
    ("Immich", "http://localhost:2283"),
    ("Ollama", "http://localhost:11435"),
    ("Element", "http://localhost:8011"),
]


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

        self.navigationstitel = [titel for titel, _url in PROGRAMM_SEITEN]

        self.stackedWidget = QStackedWidget(parent)
        self.stackedWidget.setObjectName("stackedWidget")
        for titel, url in PROGRAMM_SEITEN:
            if url is None:
                self.stackedWidget.addWidget(VerwaltungFenster(self.stackedWidget))
                continue
            if titel == "Ollama":
                self.stackedWidget.addWidget(OllamaWidget(self.stackedWidget))
                continue
            self.stackedWidget.addWidget(ProgrammSeite(url, self.stackedWidget))

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
        aktuelle_seite = self.stackedWidget.currentWidget()
        lade_wenn_noetig = getattr(aktuelle_seite, "lade_wenn_noetig", None)
        if callable(lade_wenn_noetig):
            lade_wenn_noetig()
        self.title_frame.setze_titel(self.navigationstitel[index])
