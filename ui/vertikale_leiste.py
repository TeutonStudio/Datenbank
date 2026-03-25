import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

ICON_PATH = "./ui/icon/"
STANDARD_ICON = "Logo.png"

from typing import Callable

class VertikaleLeiste(QListWidget):
    def __init__(self, parent=None, liste: list[str] = []):
        super().__init__(parent)
        self.setObjectName("listWidget")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.liste = liste
        self.nur_icon: Callable[[bool],list[None]]
        self._breite_mit_text = 200
        self._breite_nur_icon = 55
        self.aktualisiere()
        self.setze_darstellung(False)

    def aktualisiere(self):
        self.clear()
        eintragsListe: list[Callable[[bool], None]] = []

        for text in self.liste:
            eintrag = VertikalerEintrag(text)
            
            eintragsListe.append(
                lambda nur_icon, e=eintrag: e.zeige_icon() if nur_icon else e.zeige_texticon()
            )
            
            self.addItem(eintrag)

        self.nur_icon = lambda schalter: [eintrag(schalter) for eintrag in eintragsListe]

    def neue_liste(self, liste: list[str]):
        self.liste = liste
        self.aktualisiere()

    def setze_darstellung(self, nur_icon: bool):
        #self._nur_icon = nur_icon
        breite = self._breite_nur_icon if nur_icon else self._breite_mit_text
        self.setMinimumWidth(breite)
        self.setMaximumWidth(breite)
        self.nur_icon(nur_icon)

    def _ermittle_icon_name(self, text: str) -> str:
        kandidat = f"{text.lower()}.svg"
        if os.path.exists(os.path.join(ICON_PATH, kandidat)):
            return kandidat
        return STANDARD_ICON


class VertikalerEintrag(QListWidgetItem):
    def __init__(self, text: str):
        super().__init__()
        self.text_str = text
        self.icon_str = os.path.join(ICON_PATH, text.lower(), ".svg")
        self.setSizeHint(QSize(40, 40))
    
    def zeige_texticon(self):
        self.setIcon(QIcon(self.icon_str))
        self.setText(self.text_str)
    
    def zeige_icon(self):
        self.setIcon(QIcon(self.icon_str))
        self.setText(None)

