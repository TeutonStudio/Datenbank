#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refactor: Master-Detail Logs, dynamische Spalten, eingebettete Web-UI-Öffnung je Service,
kein per-Container Start/Stop, nur globale Steuerung. Polling wie gehabt.

Getestet mit PyQt6 (Fedora Workstation 42). QWebEngine optional, aber für UI-Dialog empfohlen.

Wichtige Tasten/Buttons:
- Löschen (Entf): löscht den aktuellen Log-View.
- "Alle Logs löschen": leert alle Log-Views im Speicher.
- Global: Start, Stop, Stop & Start, plus Startskript-Logs im unteren Streifen.

Persistenz: eine interne JSON-Datei im Arbeitsverzeichnis (".lkv_state.json")
für Fenstergeometrie und Spaltensichtbarkeit.
"""

import sys
import os
import shutil
import subprocess
import json
import socket
import time
import re
import PyQt6
from pathlib import Path

from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PyQt6 import (
    QtWidgets, QtCore, QtGui, QtWebEngineWidgets
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QPlainTextEdit, QPushButton, QMessageBox,
    QHeaderView, QSplitter, QToolBar, QFileDialog, QDialog, QDialogButtonBox,
    QLabel, QLineEdit
)
from PyQt6.QtCore import QUrl, QTimer, Qt, QSize
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView

# try:
    # from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore
    # HAS_WEBENGINE = True
# except Exception:
    # QWebEngineView = None  # type: ignore
    # HAS_WEBENGINE = False

# ---------------- Hilfsfunktionen ----------------

def load_env_into_environ(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # Nur setzen, wenn nicht schon per echter Umgebungsvariable vorhanden
                os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass


def url_up(url: str, timeout: float = 1.5) -> bool:
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 500
    except HTTPError as e:
        return 300 <= e.code < 600
    except (URLError, TimeoutError, socket.timeout, ConnectionError):
        return False


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def fetch_head_or_get(url: str, timeout: float = 0.8):
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            data = r.read(512).decode("utf-8", errors="ignore")
            return r.status, ct, data
    except Exception:
        return None, "", ""


# def is_http_ui(port: int) -> bool:
    # status, ct, data = fetch_head_or_get(f"http://localhost:{port}")
    # if status and 200 <= status < 400:
        # return ("text/html" in ct.lower()) or ("<html" in data.lower())
    # return False
def is_http_ui(port: int) -> bool:
    status, ct, data = fetch_head_or_get(f"http://localhost:{port}")
    if not status:
        return False
    if status == 401:
        return True
    if 200 <= status < 400 and (("text/html" in (ct or "").lower()) or ("<html" in (data or "").lower())):
        return True
    return False


def detect_compose_cmd():
    if shutil.which("docker"):
        try:
            res = subprocess.run(["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return ["docker", "compose"]
        except Exception:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def _parse_ports_field(ports_str: str):
    publishers = []
    if not ports_str:
        return publishers
    for chunk in ports_str.split(","):
        part = chunk.strip()
        if "->" in part and "/" in part:
            try:
                left, right = part.split("->", 1)
                tgt, proto = right.split("/", 1)
                tgt_port = int(tgt)
                pub_port = int(left.split(":")[-1])
                publishers.append({
                    "PublishedPort": pub_port,
                    "TargetPort": tgt_port,
                    "Protocol": proto
                })
            except Exception:
                continue
    return publishers


def compose_ps_json(compose_cmd, cwd):
    # bevorzugt docker compose ps --format json
    try:
        r = subprocess.run(
            compose_cmd + ["ps", "--format", "json"],
            cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=7
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except Exception:
        pass
    # fallback docker ps
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{json .}}"],
            cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=7
        )
        items = []
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.splitlines():
                try:
                    obj = json.loads(line)
                    items.append({
                        "Service": "",
                        "Name": obj.get("Names", ""),
                        "State": "running",
                        "Health": "",
                        "Status": obj.get("Status", ""),
                        "Publishers": _parse_ports_field(obj.get("Ports", "")),
                    })
                except Exception:
                    continue
        return items
    except Exception:
        return []


def compose_declared_services(compose_cmd, cwd, files):
    args = compose_cmd[:]
    for f in files:
        path = os.path.join(cwd, f)
        if not os.path.exists(path):
            continue
        args += ["-f", f]
    args += ["config", "--format", "json"]
    try:
        r = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        cfg = json.loads(r.stdout)
        services = {}
        for name, props in (cfg.get("services") or {}).items():
            ports = []
            for p in props.get("ports", []) or []:
                if isinstance(p, str):
                    try:
                        host = int(p.split(":")[0])
                        tgt = int(p.split(":")[1].split("/")[0])
                        ports.append((host, tgt, "tcp"))
                    except Exception:
                        continue
                elif isinstance(p, dict):
                    hp = p.get("published")
                    tp = p.get("target")
                    proto = p.get("protocol", "tcp")
                    if hp and tp:
                        try:
                            ports.append((int(hp), int(tp), proto))
                        except Exception:
                            pass
            services[name] = {"ports": ports}
        return services
    except Exception:
        return {}


def _port_http_reachable(port: int) -> bool:
    # Zählt als erreichbar: jede HTTP-Antwort inkl. 3xx/4xx/5xx, besonders 401 (Basic-Auth)
    try:
        url = f"http://localhost:{port}"
        if url_up(url):  # akzeptiert 200..599 (über HTTPError-Path), siehe dein url_up
            return True
        # Fallback: minimale HTML/401-Erkennung
        status, ct, data = fetch_head_or_get(url)
        if status == 401:
            return True
        if status and 200 <= status < 400 and (
            "text/html" in (ct or "").lower() or "<html" in (data or "").lower()
        ):
            return True
    except Exception:
        pass
    return False


# ---------------- Konstanten ----------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "local-ai-packaged")
PROFILE = "gpu-amd"
PROJECT = "localai"

PREFIXES_TO_STRIP = (
    f"{PROJECT}-",
    "localai-",
    "supabase-",
)
INDEX_SUFFIX_RE = re.compile(r"-(\d+)$")

PROGRAMM_NAME = "Lokale KI Verwaltungseinheit"
KEEP_ALIVE = 777000
HAS_WEBENGINE = True

# ---- Login/Autologin (nur bei Supabase im eingebetteten Dialog) ----
AUTOLOGIN_USER = "verwalter"
AUTOLOGIN_PASS = "allmacht"


load_env_into_environ(os.path.join(REPO_DIR, ".env"))
AUTOLOGIN_USER = os.environ.get("DASHBOARD_USERNAME", AUTOLOGIN_USER)
AUTOLOGIN_PASS = os.environ.get("DASHBOARD_PASSWORD", AUTOLOGIN_PASS)

# Endpoints werden dynamisch entdeckt; diese Liste dient nur zur bevorzugten UI-Erkennung
PRIORITY_ENDPOINTS = [
    ("n8n", "http://localhost:5678"),
    ("Open WebUI", "http://localhost:3000"),
    ("Supabase Studio", "http://localhost:8000"),
    ("Ollama", "http://localhost:11434"),
]

# Polling
POLL_MS_STATUS_ACTIVE = 1000
POLL_MS_STATUS_IDLE = 5000
POLL_MS_URLS = 1200
POLL_MS_DISCOVERY = 2000
READY_STABLE_TICKS = 5
NOT_RESPONDING_GRACE_MS = 90_000

STATE_FILE = os.path.join(BASE_DIR, ".lkv_state.json")


def normalize_key(name: str | None) -> str:
    if not name:
        return ""
    s = name.strip().lower().replace("_", "-")
    for pref in PREFIXES_TO_STRIP:
        if s.startswith(pref):
            s = s[len(pref):]
    s = INDEX_SUFFIX_RE.sub("", s)
    return s

# ---------------- Hauptfenster ----------------

class WebDialog(QDialog):
    AUTH_PORTS = {8000, 8001, 8002}

    def __init__(self, title: str, url: str, parent=None, autouser: str | None = None, autopass: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 750)

        self._autouser = autouser
        self._autopass = autopass
        self._auto_tried = False  # nur einmal automatisch probieren

        v = QVBoxLayout(self)
        v.setContentsMargins(0,0,0,0); v.setSpacing(0)

        self._url = QUrl(url)

        if HAS_WEBENGINE:
            self.web = QWebEngineView()
            v.addWidget(self.web)
            page = self.web.page()

            if self._needs_auth(self._url):
                try:
                    page.authenticationRequired.connect(self._auth_prompt)
                    page.proxyAuthenticationRequired.connect(self._auth_prompt)
                except Exception:
                    pass

            self.web.setUrl(self._url)
        else:
            v.addWidget(QLabel("QWebEngine nicht verfügbar. Bitte extern öffnen."))

    def _needs_auth(self, qurl: QUrl) -> bool:
        host = (qurl.host() or "").lower()
        port = qurl.port()
        s = qurl.toString().lower()
        if "supabase" in s or "kong" in s:
            return True
        if port in self.AUTH_PORTS and host in ("localhost", "127.0.0.1", "::1"):
            return True
        return False

    def _auth_prompt(self, req_url, authenticator):
        # 1) Automatisch mit .env-Creds versuchen (einmal)
        if not self._auto_tried and self._autouser and self._autopass:
            self._auto_tried = True
            try:
                authenticator.setUser(self._autouser)
                authenticator.setPassword(self._autopass)
                return
            except Exception:
                pass  # Fallback auf manuellen Dialog

        # 2) Manueller Dialog (sauber mit QLineEdit als Passwortfeld)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Anmeldung erforderlich - {req_url.host()}")
        lay = QVBoxLayout(dlg)
        info = QLabel(f"Die Seite {req_url.toString()} erfordert eine Anmeldung.")
        info.setWordWrap(True)
        lay.addWidget(info)

        u_label = QLabel("Benutzername:")
        u_edit = QLineEdit();  u_edit.setText(self._autouser or "")
        p_label = QLabel("Passwort:")
        p_edit = QLineEdit();  p_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if self._autopass:
            p_edit.setText(self._autopass)

        row1 = QHBoxLayout(); row1.addWidget(u_label); row1.addWidget(u_edit)
        row2 = QHBoxLayout(); row2.addWidget(p_label); row2.addWidget(p_edit)
        lay.addLayout(row1); lay.addLayout(row2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dlg)
        lay.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                authenticator.setUser(u_edit.text().strip())
                authenticator.setPassword(p_edit.text())
            except Exception:
                pass



class HauptFenster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(PROGRAMM_NAME)
        self.resize(1280, 800)

        self.compose_cmd = detect_compose_cmd()
        if not self.compose_cmd:
            self._show_compose_missing_dialog()
            # ohne Compose kein Betrieb
            return
        self._check_docker_permission()

        # State
        self.svc_proc = None
        self.svc_timer = None
        self.svc_start_time = 0.0
        self.shutting_down = False

        self.service_rows = {}  # key(normalized)->row
        self.declared_key_map = {}

        # Root Splitter: links Tabelle, rechts Log-Viewer (schließbar)
        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        splitter.addWidget(left)

        # Toolbar mit Global-Buttons und Log-Steuerung
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        act_start = QAction("Start", self)
        act_start.triggered.connect(self.onStart)
        self.toolbar.addAction(act_start)

        act_stop = QAction("Stop", self)
        act_stop.triggered.connect(self.onStop)
        self.toolbar.addAction(act_stop)

        act_restart = QAction("Stop & Start", self)
        act_restart.triggered.connect(self.onRestart)
        self.toolbar.addAction(act_restart)

        self.toolbar.addSeparator()

        act_clear_current = QAction("Log leeren", self)
        act_clear_current.triggered.connect(self.clear_current_log)
        self.toolbar.addAction(act_clear_current)

        act_clear_all = QAction("Alle Logs löschen", self)
        act_clear_all.triggered.connect(self.clear_all_logs)
        self.toolbar.addAction(act_clear_all)

        # Tabelle
        self.status_table = QTableWidget(0, 6)
        self.status_table.setHorizontalHeaderLabels(["Service", "Container", "Ports", "Status", "UI", "Aktionen"])
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.status_table, 1)

        # Rechts: Log-Viewer (Master-Detail), schließbar
        self.log_panel = QWidget()
        right_layout = QVBoxLayout(self.log_panel)
        self.log_header = QLabel("Logs: –")
        right_layout.addWidget(self.log_header)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Container-Logs erscheinen hier. Zeile wählen oder in der Tabelle auf \"Logs\" klicken.")
        right_layout.addWidget(self.log_view, 1)

        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # Startskript-Log unten (global)
        self.global_log = QPlainTextEdit()
        self.global_log.setReadOnly(True)
        self.global_log.setPlaceholderText("Start/Stop/Restart Ausgaben")
        left_layout.addWidget(self.global_log, 0)

        # Aktionen in der Tabelle
        self.status_table.cellClicked.connect(self._cell_clicked)

        # Initiale Services
        declared = {}
        declared.update(compose_declared_services(
            self.compose_cmd, REPO_DIR, ["docker-compose.yml", "docker-compose.override.private.yml"]
        ))
        supa = compose_declared_services(
            self.compose_cmd, REPO_DIR, ["supabase/docker/docker-compose.yml"]
        )
        for k, v in supa.items():
            declared.setdefault(k, v)
        for svc_name in declared.keys():
            self.declared_key_map[normalize_key(svc_name)] = svc_name
        self._populate_initial_rows(declared)

        # Timer
        self.ready_ticks = 0
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(POLL_MS_STATUS_ACTIVE)
        self.status_timer.timeout.connect(self.refresh_status_table)
        self.status_timer.start()

        self.discovery_timer = QTimer(self)
        self.discovery_timer.setInterval(POLL_MS_DISCOVERY)
        self.discovery_timer.timeout.connect(self.discover_endpoints)
        self.discovery_timer.start()

        # Keepalive
        self.keepalive_timer = QTimer(self)
        self.keepalive_timer.setInterval(KEEP_ALIVE)
        self.keepalive_timer.timeout.connect(lambda: None)
        self.keepalive_timer.start()

        # Shortcuts: Entf löscht aktuellen Log
        self.log_view.installEventFilter(self)

        # Persistenz laden
        self._load_state(splitter)

        # Buttons initial
        self._update_global_buttons(repo_running=False)
        self._ui_health = {} 
    
    def _update_ui_button(self, row: int, port: int):
        ok = _port_http_reachable(port)

        # Health-Zähler: +1 bei Erfolg, -1 bei Misserfolg, begrenzen
        score = self._ui_health.get(row, 0)
        score += 1 if ok else -1
        if score > 3: score = 3
        if score < -3: score = -3
        self._ui_health[row] = score

        btn = self.status_table.cellWidget(row, 4)
        if isinstance(btn, QPushButton):
            # Einschalten schon bei leicht positivem Score,
            # Ausschalten erst, wenn wir 3x hintereinander Fail hatten.
            if score >= 1:
                btn.setEnabled(True)
            elif score <= -3:
                btn.setEnabled(False)



    # ---------------- Persistenz ----------------
    def _load_state(self, splitter: QSplitter):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    st = json.load(f)
                geom = st.get("geometry")
                if geom and isinstance(geom, list):
                    self.resize(*geom)
                sizes = st.get("splitter")
                if sizes and isinstance(sizes, list):
                    splitter.setSizes(sizes)
        except Exception:
            pass

    def _save_state(self, splitter: QSplitter):
        try:
            st = {
                "geometry": [self.width(), self.height()],
                "splitter": splitter.sizes() if isinstance(self.centralWidget(), QSplitter) else [],
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(st, f, indent=2)
        except Exception:
            pass

    # ---------------- UI Helpers ----------------
    def _append_global_log(self, text: str):
        self.global_log.appendPlainText(text)
        QApplication.processEvents()

    def _append_container_log(self, container: str, line: str):
        # Einfacher Single-Viewer: nur der aktuell ausgewählte Container wird angezeigt
        self.log_view.appendPlainText(line)

    def _show_compose_missing_dialog(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Docker Compose fehlt")
        msg.setText("Weder 'docker compose' noch 'docker-compose' gefunden.")
        msg.setInformativeText("Installationshinweis (Fedora):\n sudo dnf install -y moby-engine docker-compose-plugin\n sudo systemctl enable --now docker")
        msg.exec()

    def _check_docker_permission(self):
        try:
            r = subprocess.run(["docker", "ps"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=5)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or "Unbekannter Fehler")
        except Exception as e:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Docker-Berechtigungen")
            msg.setText("Docker ist nicht ohne Root-Rechte nutzbar.")
            msg.setInformativeText(
                "Füge den Benutzer der 'docker'-Gruppe hinzu und melde dich neu an.\n"
                "Beispiel: sudo usermod -aG docker $USER"
            )
            msg.setDetailedText(str(e))
            msg.exec()

    # ---------------- Tabellenbefüllung ----------------
    def _populate_initial_rows(self, declared_services: dict):
        for svc_name, info in declared_services.items():
            norm_key = normalize_key(svc_name)
            if norm_key in self.service_rows:
                continue
            row = self.status_table.rowCount()
            self.status_table.insertRow(row)
            self.service_rows[norm_key] = row

            ports = ""
            for hp, tp, proto in info.get("ports", []):
                ports += f"{hp}->{tp}/{proto}, "
            ports = ports[:-2] if ports.endswith(", ") else ports

            # Service | Container | Ports | Status | UI | Aktionen
            self._set_row(row, svc_name, "", ports, "Inaktiv", ui_enabled=False)

        self._recompute_dynamic_columns()
    
    def _set_row(self, row: int, service: str, container: str, ports: str, status: str, ui_enabled: bool | None):
        def item(text):
            it = QTableWidgetItem(text or "")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return it

        self.status_table.setItem(row, 0, item(service))
        self.status_table.setItem(row, 1, item(container))
        self.status_table.setItem(row, 2, item(ports))
        self.status_table.setItem(row, 3, item(status))

        ui_btn = self.status_table.cellWidget(row, 4)
        if not isinstance(ui_btn, QPushButton):
            ui_btn = QPushButton("Öffnen")
            ui_btn.clicked.connect(lambda _=False, r=row: self._open_ui_for_row(r))
            self.status_table.setCellWidget(row, 4, ui_btn)

        # Nur setzen, wenn explizit übergeben. Sonst Zustand beibehalten (Hysterese!).
        if ui_enabled is not None:
            ui_btn.setEnabled(ui_enabled)

        act_btn = self.status_table.cellWidget(row, 5)
        if not isinstance(act_btn, QPushButton):
            act_btn = QPushButton("Logs")
            act_btn.clicked.connect(lambda _=False, r=row: self._show_logs_for_row(r))
            self.status_table.setCellWidget(row, 5, act_btn)

        # ... Farb-Logik unverändert

    # def _set_row(self, row: int, service: str, container: str, ports: str, status: str, ui_enabled: bool):
        # def item(text):
            # it = QTableWidgetItem(text or "")
            # it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # return it

        # self.status_table.setItem(row, 0, item(service))
        # self.status_table.setItem(row, 1, item(container))
        # self.status_table.setItem(row, 2, item(ports))
        # self.status_table.setItem(row, 3, item(status))

        # UI-Button
        # ui_btn = QPushButton("Öffnen")
        # ui_btn.setEnabled(ui_enabled)
        # ui_btn.clicked.connect(lambda _=False, r=row: self._open_ui_for_row(r))
        # self.status_table.setCellWidget(row, 4, ui_btn)

        # Aktionen: Logs öffnen
        # act_btn = QPushButton("Logs")
        # act_btn.clicked.connect(lambda _=False, r=row: self._show_logs_for_row(r))
        # self.status_table.setCellWidget(row, 5, act_btn)

        # Farbe je Status
        st = (status or "").lower()
        ok = ("up" in st) or ("running" in st)
        for c in range(6):
            it = self.status_table.item(row, c)
            if not it:
                continue
            if ok:
                it.setForeground(Qt.GlobalColor.darkGreen)
            elif "starting" in st or "restart" in st or "init" in st:
                it.setForeground(Qt.GlobalColor.darkYellow)
            else:
                it.setForeground(Qt.GlobalColor.red)

    def _recompute_dynamic_columns(self):
        # Dynamik-Regel: Spalten verbergen, wenn in allen Zeilen leer
        col_count = self.status_table.columnCount()
        non_empty = [False] * col_count
        for r in range(self.status_table.rowCount()):
            for c in range(col_count):
                if c in (4, 5):  # Buttons gelten als Inhalt
                    non_empty[c] = True
                    continue
                it = self.status_table.item(r, c)
                if it and it.text().strip():
                    non_empty[c] = True
        for c in range(col_count):
            self.status_table.setColumnHidden(c, not non_empty[c])

    # ---------------- Events ----------------
    def eventFilter(self, obj, ev):
        # Löscht den aktuellen Log bei Entf; vermeidet fehlerhafte .name()-Nutzung
        if obj is self.log_view:
            try:
                if ev.key() == Qt.Key.Key_Delete:
                    self.clear_current_log()
                    return True
            except AttributeError:
                # Kein Key-Event, normal weiterreichen
                pass
        return super().eventFilter(obj, ev)


    # ---------------- Actions ----------------
    def _row_to_container(self, row: int) -> str:
        it = self.status_table.item(row, 1)
        return it.text() if it else ""

    def _row_to_service(self, row: int) -> str:
        it = self.status_table.item(row, 0)
        return it.text() if it else ""

    def _row_to_ui_url(self, row: int) -> str | None:
        # aus Ports Spalte das erste Mapping nehmen: host->target/proto
        it = self.status_table.item(row, 2)
        if not it:
            return None
        txt = it.text().strip()
        if not txt: return None
        # Format: "HOST->TARGET/proto, ..."; wir nehmen erstes
        
        service = self._row_to_service(row).lower()
        if "neo4j" in service: return f"http://localhost:7474"
        
        first = txt.split(",")[0].strip()
        try:
            host_part = first.split("->")[0].strip()
            host_port = int(host_part)
            return f"http://localhost:{host_port}"
        except Exception:
            return None

    def _open_ui_for_row(self, row: int):
        url = self._row_to_ui_url(row)
        if not url:
            return
        try:
            port = int(url.split(":")[-1])
        except Exception:
            port = None
        if not (url_up(url) or (port and is_http_ui(port))):
            QMessageBox.information(self, "Nicht erreichbar", f"{url} antwortet nicht.")
            return
        title = self._row_to_service(row) or "UI"
        dlg = WebDialog(title, url, self, autouser=AUTOLOGIN_USER, autopass=AUTOLOGIN_PASS)
        dlg.exec()

    # def _auth_prompt(self, req_url, authenticator):
        # # Einfache Username/Password-Abfrage wie im Browser
        # dlg = QDialog(self)
        # dlg.setWindowTitle(f"Anmeldung erforderlich - {req_url.host()}")
        # lay = QVBoxLayout(dlg)
        # info = QLabel(f"Die Seite {req_url.toString()} erfordert eine Anmeldung.")
        # info.setWordWrap(True)
        # lay.addWidget(info)

        # row = QHBoxLayout()
        # u_label = QLabel("Benutzername:")
        # u_edit = QPlainTextEdit()
        # u_edit.setMaximumHeight(28)
        # p_label = QLabel("Passwort:")
        # p_edit = QPlainTextEdit()
        # p_edit.setMaximumHeight(28)
        # p_edit.setPlainText("")  # kein EchoMode in QPlainTextEdit, dafür kurzer Workaround unten
        # # Passwort-Echo simulieren: nutze QLineEdit wenn du magst; hier minimalistischer Ansatz:
        # # Wenn du lieber QLineEdit willst, ersetze QPlainTextEdit durch QLineEdit und setEchoMode(QLineEdit.Password)

        # form = QVBoxLayout()
        # row1 = QHBoxLayout(); row1.addWidget(u_label); row1.addWidget(u_edit)
        # row2 = QHBoxLayout(); row2.addWidget(p_label); row2.addWidget(p_edit)
        # form.addLayout(row1); form.addLayout(row2)
        # lay.addLayout(form)

        # buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dlg)
        # lay.addWidget(buttons)
        # buttons.accepted.connect(dlg.accept)
        # buttons.rejected.connect(dlg.reject)

        # if dlg.exec() == QDialog.DialogCode.Accepted:
            # user = u_edit.toPlainText().strip()
            # pwd = p_edit.toPlainText()
            # try:
                # authenticator.setUser(user)
                # authenticator.setPassword(pwd)
            # except Exception:
                # pass


    def _show_logs_for_row(self, row: int):
        container = self._row_to_container(row)
        if not container:
            # versuche Service-Name als Container
            container = normalize_key(self._row_to_service(row))
        if not container:
            return
        self._start_log_stream(container)

    # ---------------- Log Stream ----------------
    def _start_log_stream(self, container: str):
        # kill alten Prozess
        if hasattr(self, "log_proc") and self.log_proc is not None:
            try:
                self.log_proc.kill()
            except Exception:
                pass
            self.log_proc = None

        from PyQt6.QtCore import QProcess
        self.log_proc = QProcess(self)
        # Alle Logs, follow. Das kann viel sein; Docker puffert sinnvoll.
        self.log_proc.setProgram("docker")
        self.log_proc.setArguments(["logs", "-f", container])
        self.log_proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.log_proc.readyReadStandardOutput.connect(lambda: self._drain_log_output(container))
        self.log_proc.started.connect(lambda: self._on_log_started(container))
        self.log_proc.errorOccurred.connect(lambda _err: self._append_container_log(container, "[Fehler beim Start des Log-Streams]"))
        self.log_proc.start()

    def _on_log_started(self, container: str):
        self.log_header.setText(f"Logs: {container}")
        self.log_view.clear()

    def _drain_log_output(self, container: str):
        try:
            data = self.log_proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            if data:
                self._append_container_log(container, data.rstrip("\n"))
        except Exception:
            pass

    def clear_current_log(self):
        self.log_view.clear()

    def clear_all_logs(self):
        # Bei Single-Viewer identisch mit clear_current
        self.log_view.clear()

    # ---------------- Start/Stop/Restart ----------------
    def _update_global_buttons(self, repo_running: bool):
        # toolbar Buttons sind immer klickbar; keine dynamische Deaktivierung nötig.
        pass

    def onStart(self):
        if self.svc_proc and self.svc_proc.poll() is None:
            return
        self._append_global_log(f"Starte Services in {REPO_DIR} mit Profil {PROFILE} ...")
        try:
            self.svc_proc = subprocess.Popen(
                ["python3", "start_services.py", "--profile", PROFILE],
                cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            self.svc_start_time = time.time()
            if self.svc_timer is None:
                self.svc_timer = QTimer(self)
                self.svc_timer.setInterval(100)
                self.svc_timer.timeout.connect(self._drain_service_output)
                self.svc_timer.start()
        except Exception as e:
            self._append_global_log(f"Fehler beim Starten der Services:\n{e}")

    def onStop(self):
        self._append_global_log("[Stop] Beende Stacks per docker compose down ...")
        self.setEnabled(False)
        try:
            self._run_down_sequence()
        finally:
            self.setEnabled(True)

    def onRestart(self):
        self._append_global_log("[Restart] Down ...")
        self.setEnabled(False)
        try:
            self._run_down_sequence()
        finally:
            self.setEnabled(True)
        self.onStart()

    def _run_down_sequence(self):
        cmds = [
            (self.compose_cmd + ["-p", PROJECT, "-f", "docker-compose.yml", "-f", "docker-compose.override.private.yml", "down", "--remove-orphans"], REPO_DIR),
            (self.compose_cmd + ["-p", PROJECT, "-f", "supabase/docker/docker-compose.yml", "down", "--remove-orphans"], REPO_DIR),
        ]
        deadline = time.time() + (NOT_RESPONDING_GRACE_MS / 1000.0)
        for cmd, cwd in cmds:
            filtered_cmd = []
            skip_next = False
            for i, part in enumerate(cmd):
                if skip_next:
                    skip_next = False
                    continue
                if part == "-f":
                    path = os.path.join(cwd, cmd[i+1])
                    if not os.path.exists(path):
                        self._append_global_log(f"[Info] Überspringe fehlende Compose-Datei: {cmd[i+1]}")
                        skip_next = True
                        continue
                filtered_cmd.append(part)

            self._append_global_log("Running: " + " ".join(filtered_cmd))
            proc = subprocess.Popen(filtered_cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            last_pulse = time.time()
            while True:
                line = proc.stdout.readline()
                if line:
                    self._append_global_log(line.rstrip("\n"))
                if proc.poll() is not None:
                    break
                QApplication.processEvents()
                if time.time() - last_pulse > 0.5:
                    last_pulse = time.time()
                if time.time() > deadline:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    break
            rc = proc.poll()
            self._append_global_log(f"[down beendet] rc={rc}")

    def _drain_service_output(self):
        if not self.svc_proc or self.svc_proc.stdout is None:
            return
        try:
            got = False
            while True:
                line = self.svc_proc.stdout.readline()
                if not line:
                    break
                got = True
                self._append_global_log(line.rstrip("\n"))
            if not got and (time.time() - getattr(self, "svc_start_time", time.time())) < (NOT_RESPONDING_GRACE_MS / 1000):
                QApplication.processEvents()
        except Exception as e:
            self._append_global_log(f"[Service-Output Fehler] {e}")
        if self.svc_proc.poll() is not None:
            self._append_global_log("[start_services.py beendet]")
            if self.svc_timer:
                self.svc_timer.stop()

    # ---------------- Status/Discovery ----------------
    def refresh_status_table(self):
        items = compose_ps_json(self.compose_cmd, REPO_DIR)
        any_running = False

        # Map: key -> row
        for it in items:
            raw_service = it.get("Service", "") or ""
            raw_name = it.get("Name", "") or ""
            state = it.get("State", "") or ""
            status = it.get("Status", "") or ""

            pubs = it.get("Publishers") or []
            ports = ""
            if isinstance(pubs, list) and pubs:
                ports = ", ".join([f"{p.get('PublishedPort','')}->{p.get('TargetPort','')}/{p.get('Protocol','')}" for p in pubs if p])

            norm_service = normalize_key(raw_service)
            norm_name = normalize_key(raw_name)

            if norm_service in self.declared_key_map:
                key = norm_service
                disp_service = self.declared_key_map[norm_service]
            elif norm_name in self.declared_key_map:
                key = norm_name
                disp_service = self.declared_key_map[norm_name]
            else:
                key = norm_service or norm_name or f"row-{self.status_table.rowCount()}"
                disp_service = norm_service or norm_name

            if key in self.service_rows:
                row = self.service_rows[key]
                ui_enabled = False
                url = None
                # genau ein Port je Zeile, falls vorhanden: wir aktivieren, wenn erreichbar
                if ports:
                    try:
                        host_port = int(ports.split(",")[0].split("->")[0])
                        # url = f"http://localhost:{host_port}"
                        # ui_enabled = url_up(url) or is_http_ui(host_port)
                        self._update_ui_button(row, host_port)
                    except Exception: pass
                        # ui_enabled = False
                self._set_row(row, disp_service, raw_name, ports, status or state, ui_enabled)
            else:
                row = self.status_table.rowCount()
                self.status_table.insertRow(row)
                self.service_rows[key] = row
                self._set_row(row, disp_service, raw_name, ports, status or state, ui_enabled=False)

            st_low = (state or status).lower()
            if ("up" in st_low) or ("running" in st_low):
                any_running = True

        # dynamische Spalten neu berechnen
        self._recompute_dynamic_columns()

        # Ready-Logik
        if self._stack_ready(items):
            self.ready_ticks += 1
        else:
            self.ready_ticks = 0
        if self.ready_ticks >= READY_STABLE_TICKS:
            if self.status_timer.interval() != POLL_MS_STATUS_IDLE:
                self.status_timer.setInterval(POLL_MS_STATUS_IDLE)
                self._append_global_log("[OK] Stack stabil. Status-Polling auf 5s gedrosselt.")

    def _stack_ready(self, items):
        # bereit: keine Container im schlechten Zustand
        for it in items:
            st = (it.get("State", "") or "").lower()
            if st and not ("running" in st or "up" in st):
                return False
        return True

    def discover_endpoints(self):
        # Nicht mehr als Extra-Tabs, nur zum Aktivieren des UI-Buttons wenn HTML
        items = compose_ps_json(self.compose_cmd, REPO_DIR)
        for it in items:
            pubs = it.get("Publishers") or []
            name = it.get("Service") or it.get("Name") or "Service"
            norm = normalize_key(name)
            if norm not in self.service_rows:
                continue
            row = self.service_rows[norm]
            ui_btn = self.status_table.cellWidget(row, 4)
            if not isinstance(ui_btn, QPushButton):
                continue
            # genau ein Port → aktivieren, wenn HTML
            if pubs:
                try:
                    p = int(pubs[0].get("PublishedPort"))
                    # ui_btn.setEnabled(is_http_ui(p))
                    self._update_ui_button(row, p)
                except Exception: pass

    # ---------------- Table interactions ----------------
    def _cell_clicked(self, row: int, col: int):
        # Auswahl aktualisiert Headline
        cont = self._row_to_container(row)
        if cont:
            self.log_header.setText(f"Logs: {cont}")

    # ---------------- Closing ----------------
    def closeEvent(self, event):
        # speichere State
        if isinstance(self.centralWidget(), QSplitter):
            self._save_state(self.centralWidget())

        # if self.shutting_down:
            # event.accept()
            # return
        # self.shutting_down = True
        # self._append_global_log("[Beenden] Stoppe Stacks per docker compose down ...")
        # self.setEnabled(False)
        # try:
            # self._run_down_sequence()
        # finally:
            # self.setEnabled(True)
        event.accept()

def install_requirement():
    def run(cmd):
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Command failed: {cmd}")
            raise e

    # 1. pip sicherstellen
    try:
        import pip  # noqa
        print("[OK] pip ist vorhanden")
    except ImportError:
        print("[INFO] pip fehlt, versuche Installation...")
        try:
            import ensurepip
            ensurepip.bootstrap()
            print("[OK] pip wurde installiert")
        except Exception as e:
            print("[ERROR] Konnte pip nicht installieren")
            raise e

    # 2. Python-Pakete prüfen/installieren
    required_packages = ["PyQt6","PyQt6-WebEngine"]

    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"[OK] {package} ist bereits installiert")
        except ImportError:
            print(f"[INFO] Installiere {package}...")
            run([sys.executable, "-m", "pip", "install", "--user", package])

    # 3. docker-compose prüfen (systemweit)
    if shutil.which("docker-compose") or shutil.which("docker compose"):
        print("[OK] docker-compose ist vorhanden")
    else:
        print("[WARN] docker-compose nicht gefunden.")
        print("       Bitte manuell installieren (z.B. via apt, pacman, etc.)")
        # absichtlich KEIN Auto-Install, weil:
        # - braucht root
        # - distro-spezifisch
        # - du willst dein System nicht von Python-Skripten verwalten lassen

    print("[DONE] Abhängigkeiten geprüft")
    

if __name__ == "__main__":
    install_requirement()
    app = QApplication(sys.argv)
    win = HauptFenster()
    win.show()
    sys.exit(app.exec())

