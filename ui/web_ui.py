import sys
import os
import shutil
import subprocess
import json
import socket
import time
import re
import PyQt6

from PyQt6 import (
    QtWidgets, QtCore, QtGui, QtWebEngineWidgets
)
from PyQt6.QtWidgets import (
    QApplication, QGridLayout, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QPlainTextEdit, QPushButton, QMessageBox,
    QHeaderView, QSplitter, QToolBar, QFileDialog, QDialog, QDialogButtonBox,
    QLabel, QLineEdit, QListWidgetItem
)
from PyQt6.QtCore import QUrl, QTimer, Qt, QSize
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

# TODO Websiten auth einbauen

class ProgrammSeite(QWebEngineView):
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setUrl(QUrl(url))