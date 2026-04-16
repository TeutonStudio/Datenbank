import os
import sys

if "FONTCONFIG_FILE" not in os.environ and os.path.exists("/etc/fonts/fonts.conf"):
    os.environ["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"

from PyQt6.QtWidgets import QApplication
from Schnittstelle.haupt_fenster import HauptFenster


class Anwendung(QApplication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open("style.qss") as f:
            self.setStyleSheet(f.read())
        self.fenster = HauptFenster()
        self.fenster.show()

if __name__ == "__main__":
    app = Anwendung(sys.argv)
    sys.exit(app.exec())
