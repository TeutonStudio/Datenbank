import os
import sys
from pathlib import Path

if "FONTCONFIG_FILE" not in os.environ and os.path.exists("/etc/fonts/fonts.conf"):
    os.environ["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"

from PyQt6.QtWidgets import QApplication
from Schnittstelle.haupt_fenster import HauptFenster


class Anwendung(QApplication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with (Path(__file__).resolve().parent / "style.qss").open(encoding="utf-8") as f:
            self.setStyleSheet(f.read())
        self.fenster = HauptFenster()
        self.fenster.show()

if __name__ == "__main__":
    app = Anwendung(sys.argv)
    sys.exit(app.exec())
