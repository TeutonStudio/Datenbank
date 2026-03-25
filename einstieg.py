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

def requirement():
    list = [
        "PyQt6",
        "PyQt6-WebEngine",
    ]
    for r in list: subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", r])

if __name__ == "__main__":
    requirement()
    app = QApplication(sys.argv)
    # Load style file
    with open("style.qss") as f: style_str = f.read()
    app.setStyleSheet(style_str)
    win = HauptFenster()
    win.show()
    sys.exit(app.exec())