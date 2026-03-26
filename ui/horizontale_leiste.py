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
    QLabel, QLineEdit, QListWidgetItem, QFrame
)
from PyQt6.QtCore import QUrl, QTimer, Qt, QSize
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

from typing import Callable

class HorizontaleLeiste(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("title_frame")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        
        self.horizontalLayout = QtWidgets.QHBoxLayout(self)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.title_icon = QtWidgets.QLabel(parent=self)
        self.title_icon.setObjectName("title_icon")
        
        self.title_label = QtWidgets.QLabel(parent=self)
        self.title_label.setObjectName("title_label")
        
        self.menu_btn = QtWidgets.QPushButton(parent=self)
        self.menu_btn.setObjectName("menu_btn")
        
        self.horizontalLayout.addWidget(self.title_icon)
        self.horizontalLayout.addWidget(self.title_label)
        self.horizontalLayout.addWidget(self.menu_btn)
        self.horizontalLayout.addStretch()
        
        self.title_icon.setText("")
        self.title_icon.setPixmap(QPixmap("./ui/icon/Logo.png"))
        self.title_icon.setScaledContents(True)
        
        self.menu_btn.setText("")
        self.menu_btn.setIcon(QIcon("./ui/icon/close.svg"))
        self.menu_btn.setIconSize(QSize(30, 30))
        self.menu_btn.setCheckable(True)
        self.menu_btn.setChecked(False)
        
        self.setze_titel("Abschnitt")
    
    def setze_titel(self, titel: str):
        self.title_label.setText(titel)

    def button_icon_change(self, status):
        pfad = "./ui/icon/" + ("open" if status else "close") + ".svg"
        self.menu_btn.setIcon(QIcon(pfad))

    def init_single_slot(self, side_menu, setCurrentIndex):
        self.menu_btn.toggled['bool'].connect(side_menu.setze_darstellung)
        self.menu_btn.toggled['bool'].connect(self.title_label.setHidden)
        side_menu.currentRowChanged['int'].connect(setCurrentIndex)
        self.menu_btn.toggled.connect(self.button_icon_change)