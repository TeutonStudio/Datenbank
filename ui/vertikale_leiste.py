import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

ICON_PATH = "./ui/icon/"

BREITE = { "nur_icon": 55, "mit_text": 200 }

from typing import Callable

class VertikaleLeiste(QListWidget):
    def __init__(self, parent=None, liste: list[str] = []):
        super().__init__(parent)
        self.setObjectName("listWidget")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nur_icon: Callable[[bool],list[None]]
        self.liste: list[str]
        
        self.neue_liste(liste)
        self.aktualisiere()
        self.setze_darstellung(False)

    def aktualisiere(self):
        self.clear()
        eintragsListe: list[Callable[[bool], None]] = []

        for text in self.liste:
            eintrag = VertikalerEintrag(text)
            self.addItem(eintrag)
            eintragsListe.append(
                lambda nur_icon, e=eintrag: e.zeige_icon() if nur_icon else e.zeige_texticon()
            )

        self.nur_icon = lambda schalter: [eintrag(schalter) for eintrag in eintragsListe]

    def neue_liste(self, liste: list[str]):
        self.liste = liste
        self.aktualisiere()

    def setze_darstellung(self, nur_icon: bool):
        #self._nur_icon = nur_icon
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
        else: pfad = "./ui/icon/settings.svg"
        self.setIcon(QIcon(pfad))
        self.setSizeHint(QSize(40, 40))
    
    def zeige_texticon(self):
        self.definiere_icon()
        self.setText(self.text_str)
    
    def zeige_icon(self):
        self.definiere_icon()
        self.setText(None)

