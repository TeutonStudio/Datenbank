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

from ui.vertikale_leiste import VertikaleLeiste

PROGRAMM_NAME = "N8N Verwalter"


class HauptFenster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1280, 800)
        self.central_widget = QWidget(parent=self)
        self.central_widget.setObjectName("centralwidget")
        self.gridLayout = QtWidgets.QGridLayout(self.central_widget)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.gridLayout.setColumnStretch(1, 1)

        self.title_frame = QtWidgets.QFrame(parent=self.central_widget)
        self.title_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.title_frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.title_frame.setObjectName("title_frame")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.title_frame)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_icon = QtWidgets.QLabel(parent=self.title_frame)
        self.title_icon.setObjectName("title_icon")
        self.horizontalLayout.addWidget(self.title_icon)
        self.title_label = QtWidgets.QLabel(parent=self.title_frame)
        self.title_label.setObjectName("title_label")
        self.horizontalLayout.addWidget(self.title_label)
        self.menu_btn = QtWidgets.QPushButton(parent=self.title_frame)
        self.menu_btn.setObjectName("menu_btn")
        self.horizontalLayout.addWidget(self.menu_btn)
        self.horizontalLayout.addStretch()
        self.gridLayout.addWidget(self.title_frame, 0, 0, 1, 2)

        self.stackedWidget = QtWidgets.QStackedWidget(parent=self.central_widget)
        self.stackedWidget.setObjectName("stackedWidget")
        self.page = QtWidgets.QWidget()
        self.page.setObjectName("page")
        self.stackedWidget.addWidget(self.page)
        self.page_2 = QtWidgets.QWidget()
        self.page_2.setObjectName("page_2")
        self.stackedWidget.addWidget(self.page_2)
        self.gridLayout.addWidget(self.stackedWidget, 1, 1, 1, 1)

        self.listWidget = VertikaleLeiste(parent=self.central_widget,liste=[
            "Verwaltung", # TODO icon definieren
            "N8N", # TODO icon definieren
        ])
        self.gridLayout.addWidget(self.listWidget, 1, 0, 1, 1)

        self.setCentralWidget(self.central_widget)
        self.menubar = QtWidgets.QMenuBar(parent=self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 875, 22))
        self.menubar.setObjectName("menubar")
        self.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(parent=self)
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)

        self.retranslateUi(self)
        QtCore.QMetaObject.connectSlotsByName(self)

        self.setWindowIcon(QIcon("./ui/icon/Logo.png"))
        self.setWindowTitle(PROGRAMM_NAME)

        self.title_label.setText("CodeQuestions")

        self.title_icon.setText("")
        self.title_icon.setPixmap(QPixmap("./ui/icon/Logo.png"))
        self.title_icon.setScaledContents(True)

        self.side_menu = self.listWidget

        self.menu_btn.setText("")
        self.menu_btn.setIcon(QIcon("./ui/icon/close.svg"))
        self.menu_btn.setIconSize(QSize(30, 30))
        self.menu_btn.setCheckable(True)
        self.menu_btn.setChecked(False)

        self.main_content = self.stackedWidget

        self.init_list_widget()
        self.init_stackwidget()
        self.init_single_slot()

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.title_icon.setText(_translate("MainWindow", "TextLabel"))
        self.title_label.setText(_translate("MainWindow", "TextLabel"))
        self.menu_btn.setText(_translate("MainWindow", "PushButton"))

    def init_single_slot(self):
        self.menu_btn.toggled['bool'].connect(self.side_menu.setze_darstellung)
        self.menu_btn.toggled['bool'].connect(self.title_label.setHidden)
        self.side_menu.currentRowChanged['int'].connect(self.main_content.setCurrentIndex)
        self.menu_btn.toggled.connect(self.button_icon_change)

    def init_list_widget(self):
        self.side_menu.neue_liste([
            "Verwaltung", # TODO icon definieren
            "N8N", # TODO icon definieren
        ])
        self.side_menu.setCurrentRow(0)

    def init_stackwidget(self):
        widget_list = self.main_content.findChildren(QWidget)
        for widget in widget_list:
            self.main_content.removeWidget(widget)

#        for menu in self.menu_list:
#            text = menu.get("name")
#            layout = QGridLayout()
#            label = QLabel(text)
#            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#            font = QFont()
#            font.setPixelSize(20)
#            label.setFont(font)
#            layout.addWidget(label)
#            new_page = QWidget()
#            new_page.setLayout(layout)
#            self.main_content.addWidget(new_page)

    def button_icon_change(self, status):
        if status:
            self.menu_btn.setIcon(QIcon("./ui/icon/open.svg"))
        else:
            self.menu_btn.setIcon(QIcon("./ui/icon/close.svg"))
