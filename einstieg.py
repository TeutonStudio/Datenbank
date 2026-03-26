import sys
import os
import shutil
import subprocess
import json
import socket
import time
import re
from PyQt6.QtWidgets import QApplication
from ui.haupt_fenster import HauptFenster
class Anwendung(QApplication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open("style.qss") as f: self.setStyleSheet(f.read())
        self.fenster = HauptFenster()
        self.fenster.show()

if __name__ == "__main__":
    app = Anwendung(sys.argv)
    sys.exit(app.exec())