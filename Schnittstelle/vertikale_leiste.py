import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

ICON_PATH = "./Schnittstelle/icon/"

BREITE = { "nur_icon": 55, "mit_text": 200 }

from typing import Callable

class VertikaleLeiste(QListWidget):
    def __init__(self, parent=None, liste: list[str] | None = None):
        super().__init__(parent)
        self.setObjectName("listWidget")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nur_icon: Callable[[bool], list[None]] = lambda _schalter: []
        self.liste: list[str] = []
        self._nur_icon = False

        self.neue_liste(liste or [])

    def aktualisiere(self):
        self.clear()
        eintrag_liste: list[Callable[[bool], None]] = []

        for text in self.liste:
            vert_eintrag = VertikalerEintrag(text)
            self.addItem(vert_eintrag)
            eintrag_liste.append(vert_eintrag.schalter)

        self.nur_icon = lambda schalter: [eintrag(schalter) for eintrag in eintrag_liste]
        self.setze_darstellung(self._nur_icon)

    def neue_liste(self, liste: list[str]):
        self.liste = liste
        self.aktualisiere()

    def setze_darstellung(self, nur_icon: bool):
        self._nur_icon = nur_icon
        breite = BREITE["nur_icon" if nur_icon else "mit_text"]
        self.setMinimumWidth(breite)
        self.setMaximumWidth(breite)
        self.nur_icon(nur_icon)


class VertikalerEintrag(QListWidgetItem):
    def __init__(self, text: str):
        super().__init__()
        self.text_str = text
        self.icon_str = os.path.join(ICON_PATH, text.lower() + ".svg")
    
    def definiere_icon(self, icon_str: str | None = None):
        if icon_str: self.icon_str = icon_str
        pfad = ""
        if os.path.exists(self.icon_str): pfad = self.icon_str
        else: pfad = "./Schnittstelle/icon/settings.svg"
        self.setIcon(QIcon(pfad))
        self.setSizeHint(QSize(40, 40))

    def schalter(self,b: bool): self.zeige_icon() if b else self.zeige_texticon()

    def zeige_texticon(self):
        self.definiere_icon()
        self.setText(self.text_str)
    
    def zeige_icon(self):
        self.definiere_icon()
        self.setText(None)
