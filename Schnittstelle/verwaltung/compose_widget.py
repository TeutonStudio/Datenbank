from typing import Any

from PyQt6.QtCore import QCoreApplication, QThread, QTimer, Qt
from PyQt6.QtWidgets import QSplitter

from Kern.compose.env import Umgebungsvariablen
from Kern.podman import (
    PodmanComposeStartKonfiguration,
    PROJEKT_NAME,
    baue_startkonfiguration,
    lade_ausgewaehlte_dienste,
    lade_startkonfiguration,
    loesche_startkonfiguration,
    podman_compose_argumente,
    prozessumgebung_fuer_konfiguration,
    speichere_ausgewaehlte_dienste,
    speichere_startkonfiguration,
    startkonfigurationen_unterscheiden_sich,
)
from Schnittstelle.consolen_dialog import PodmanProzessDialog, PodmanProzessKetteDialog
from Schnittstelle.verwaltung.compose.ausgabe_widget import AusgabeBereich
from Schnittstelle.verwaltung.compose.container_widget import ContainerBereich, DienstDefinition
from Schnittstelle.verwaltung.compose.volumen_widget import VolumenBereich
from Schnittstelle.verwaltung.einstellungen_dialog import EinstellungenDialog
from Schnittstelle.verwaltung.podman_runtime import (
    HintergrundFehler,
    HintergrundWorker,
    fuehre_podman_kommando,
    lade_json_liste,
)

PodmanDialog = PodmanProzessDialog | PodmanProzessKetteDialog

DIENSTE = [
    DienstDefinition("n8n", "N8N", ("n8n",), pflichtdienst=True),
    DienstDefinition("open-webui", "Open WebUI", ("open-webui",)),
    DienstDefinition("flowise", "Flowise", ("flowise",)),
    DienstDefinition("langfuse", "Langfuse", ("langfuse-web",)),
    DienstDefinition("neo4j", "Neo4j", ("neo4j",)),
    DienstDefinition("minio", "MinIO", ("minio",)),
    DienstDefinition("searxng", "SearXNG", ("searxng",)),
    DienstDefinition("supabase", "Supabase Studio", ("studio", "supabase-studio")),
    DienstDefinition("ollama", "Ollama", ("ollama", "ollama-cpu", "ollama-gpu", "ollama-gpu-amd")),
    DienstDefinition("immich", "Immich", ("immich-server",)),
    DienstDefinition("matrix-synapse", "Matrix Synapse", ("matrix-synapse", "synapse")),
    DienstDefinition("matrix-element", "Element Web", ("matrix-element", "element")),
    DienstDefinition("tailscale", "Tailscale", ("tailscale",)),
]


# TODO vereinfachen
# TODO einen Selektor definieren, der übergreifend eines aus entweder container oder volumen auswählt (oder nichts). Dieser Selektor definiert welches log im ausgabe dargestellt wird (bei nichts ist es das des gesamten container)
# TODO Das Ausgabe widget braucht daher links von aktualisieren einen Knopf zum abwählen der aktuellen auswahl
# TODO da offenbar keine Volumenlog existent, beschränkt sich der Selektor auf container, die ausgabe ebenfalls
class ComposeWidget(QSplitter):
    def __init__(self, parent, umgebungsvariablen: Umgebungsvariablen):
        super().__init__(Qt.Orientation.Vertical,parent)
        self._projekt_pfad = parent.projekt_pfad
        self._umgebungsvariablen = umgebungsvariablen
        self._compose_status_pfad = self._projekt_pfad / ".compose.state.json"
        alter_status_pfad = self._projekt_pfad / "Schnittstelle" / ".compose.state.json"
        if not self._compose_status_pfad.exists() and alter_status_pfad.exists():
            self._compose_status_pfad = alter_status_pfad
        self._letzte_startkonfiguration = lade_startkonfiguration(
            self._compose_status_pfad
        )
        self._letzte_dienstauswahl = lade_ausgewaehlte_dienste(
            self._compose_status_pfad
        )
        self._container_status: dict[str, dict[str, object]] = {}
        self._ausgewaehlter_container: str | None = None
        self._ausgewaehlter_dienst = "Kein Dienst ausgewählt"
        self._letzter_status_fehler = ""
        self._aktualisierung_laeuft = False
        self._aktualisierung_angefordert = False
        self._log_auftrag_laeuft = False
        self._log_aktualisierung_angefordert = False
        self._log_anfrage_id = 0
        self._statusdarstellung_laeuft = False
        self._wird_beendet = False
        self._start_dialog: PodmanDialog | None = None
        self._prozess_dialoge: list[PodmanDialog] = []
        self._hintergrund_threads: list[QThread] = []
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._beende_hintergrund_threads)

        self.volumen_bereich = VolumenBereich(parent)
        self.container_bereich = ContainerBereich(DIENSTE, self)
        self.ausgabe_bereich = AusgabeBereich(parent)

        if self._letzte_dienstauswahl is not None:
            self.container_bereich.setze_auswahl(
                self._letzte_dienstauswahl,
                als_manuelle_auswahl=True,
            )
            self._letzte_dienstauswahl = tuple(
                self.container_bereich.ausgewaehlte_dienst_ids()
            )
            speichere_ausgewaehlte_dienste(
                self._compose_status_pfad,
                self._letzte_dienstauswahl,
            )

        unterer_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        unterer_splitter.addWidget(self.volumen_bereich)
        unterer_splitter.addWidget(self.container_bereich)
        unterer_splitter.setStretchFactor(0, 1)
        unterer_splitter.setStretchFactor(1, 2)

        self.addWidget(self.ausgabe_bereich)
        self.addWidget(unterer_splitter)

        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 2)

        self.container_bereich.container_gewaehlt.connect(self._setze_ausgewaehlten_container)
        self.container_bereich.dienste_schalten.connect(self._schalte_dienste)
        self.container_bereich.auswahl_geaendert.connect(self._bei_auswahl_geaendert)
        self.container_bereich.aktualisieren_angefragt.connect(self.aktualisiere_inhalt)
        self.container_bereich.einstellungen_angefragt.connect(self._oeffne_einstellungen)
        self.volumen_bereich.aktualisieren_angefragt.connect(self.aktualisiere_inhalt)
        self.ausgabe_bereich.aktualisieren_angefragt.connect(self._aktualisiere_logs)

        self._log_timer = QTimer(self)
        self._log_timer.setSingleShot(True)
        self._log_timer.setInterval(200)
        self._log_timer.timeout.connect(self._starte_log_aktualisierung)

    def aktualisiere_inhalt(self) -> None:
        if self._wird_beendet:
            return
        if self._aktualisierung_laeuft:
            self._aktualisierung_angefordert = True
            return
        self._aktualisierung_laeuft = True
        self._aktualisierung_angefordert = False
        self._starte_hintergrundauftrag(
            self._lade_status_und_volumen,
            self._status_und_volumen_geladen,
        )

    def _aktualisiere_container(self) -> None:
        self.aktualisiere_inhalt()

    def _aktualisiere_volumen(self) -> None:
        self.aktualisiere_inhalt()

    def _aktualisiere_logs(self) -> None:
        self.ausgabe_bereich.setze_ausgewaehlten_container(
            self._ausgewaehlter_container,
            self._ausgewaehlter_dienst,
        )

        if not self._ausgewaehlter_container:
            text = self._letzter_status_fehler or (
                "Für den ausgewählten Dienst wurde noch kein Podman-Container gefunden."
            )
            self.ausgabe_bereich.setze_ausgabe(text)
            return

        self._log_timer.start()

    def _setze_ausgewaehlten_container(
        self,
        container_name: str | None,
        dienst_titel: str,
    ) -> None:
        self._ausgewaehlter_container = container_name
        self._ausgewaehlter_dienst = dienst_titel
        if self._statusdarstellung_laeuft:
            return
        self._aktualisiere_logs()

    def _schalte_dienste(self, befehl: str, dienst_ids: list[str]) -> None:
        if not dienst_ids:
            self.ausgabe_bereich.setze_ausgabe(
                "Keine passenden Dienste für diese Kollektiv-Aktion ausgewählt."
            )
            return

        if befehl == "start":
            self._starte_dienste(dienst_ids)
            return

        if befehl == "restart":
            self._neustarte_dienste(dienst_ids)
            return

        self._stoppe_dienste()

    def _bei_auswahl_geaendert(self) -> None:
        self._letzte_dienstauswahl = tuple(self.container_bereich.ausgewaehlte_dienst_ids())
        speichere_ausgewaehlte_dienste(
            self._compose_status_pfad,
            self._letzte_dienstauswahl,
        )
        self._aktualisiere_containerdarstellung()

    def _aktualisiere_containerdarstellung(self) -> None:
        self._statusdarstellung_laeuft = True
        try:
            self.container_bereich.setze_status(
                self._container_status,
                self._letzter_status_fehler,
                konfiguration_geaendert=self._konfiguration_ist_geaendert(),
            )
        finally:
            self._statusdarstellung_laeuft = False

    def _konfiguration_ist_geaendert(self) -> bool:
        if not self._irgendetwas_laeuft():
            return False
        if self._letzte_startkonfiguration is None:
            return False

        aktuelle_konfiguration = self._gewuenschte_startkonfiguration()
        if aktuelle_konfiguration is None:
            return False

        return startkonfigurationen_unterscheiden_sich(
            aktuelle_konfiguration,
            self._letzte_startkonfiguration,
        )

    def _oeffne_einstellungen(self) -> None:
        dialog = EinstellungenDialog(
            self._umgebungsvariablen,
            self.container_bereich.ausgewaehlte_dienst_ids(),
            {dienst.dienst_id: dienst.titel for dienst in DIENSTE},
            self,
        )
        if dialog.exec():
            self.ausgabe_bereich.setze_ausgabe(
                f"Einstellungen gespeichert: {self._umgebungsvariablen.env_pfad.name}"
            )
            self._aktualisiere_containerdarstellung()

    def _gewuenschte_startkonfiguration(
        self,
    ) -> PodmanComposeStartKonfiguration | None:
        try:
            return baue_startkonfiguration(
                self.container_bereich.ausgewaehlte_dienst_ids(),
                self._umgebungsvariablen,
            )
        except ValueError:
            return None

    def _irgendetwas_laeuft(self) -> bool:
        return any(
            bool(status.get("laeuft")) for status in self._container_status.values()
        )

    def _starte_dienste(self, dienst_ids: list[str]) -> None:
        if self._start_dialog is not None and self._start_dialog.isVisible():
            self._start_dialog.raise_()
            self._start_dialog.activateWindow()
            return

        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        argumente = podman_compose_argumente(
            startkonfiguration,
            "up",
            "-d",
            "--remove-orphans",
        )
        dialog = PodmanProzessDialog(
            "Compose-Stack starten",
            argumente,
            self._projekt_pfad,
            prozessumgebung_fuer_konfiguration(startkonfiguration),
            timeout=600,
            parent=self,
        )
        self._start_dialog = dialog
        self._prozess_dialoge.append(dialog)
        dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
        self.container_bereich.aktions_button.setEnabled(False)
        self.ausgabe_bereich.setze_ausgabe(
            f"Compose-Stack wird gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

        def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
            self.container_bereich.aktions_button.setEnabled(True)
            if self._start_dialog is dialog:
                self._start_dialog = None

            if not erfolgreich:
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack konnte nicht gestartet werden."
                )
                return

            speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
            self._letzte_startkonfiguration = startkonfiguration
            self.aktualisiere_inhalt()
            self.ausgabe_bereich.setze_ausgabe(
                ausgabe
                or f"Compose-Stack gestartet: {', '.join(startkonfiguration.dienst_ids)}"
            )

        dialog.setze_abgeschlossen_callback(abgeschlossen)
        dialog.starten()
        dialog.open()

    def _entferne_prozess_dialog(self, dialog: PodmanDialog) -> None:
        if dialog in self._prozess_dialoge:
            self._prozess_dialoge.remove(dialog)

    def _neustarte_dienste(self, dienst_ids: list[str]) -> None:
        if self._start_dialog is not None and self._start_dialog.isVisible():
            self._start_dialog.raise_()
            self._start_dialog.activateWindow()
            return

        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        stopp_konfiguration = self._letzte_startkonfiguration or startkonfiguration
        dialog = PodmanProzessKetteDialog(
            "Compose-Stack neu starten",
            [
                (
                    "Compose-Stack wird gestoppt ...",
                    podman_compose_argumente(
                        stopp_konfiguration,
                        "down",
                        "--remove-orphans",
                    ),
                    prozessumgebung_fuer_konfiguration(stopp_konfiguration),
                ),
                (
                    "Compose-Stack wird neu gestartet ...",
                    podman_compose_argumente(
                        startkonfiguration,
                        "up",
                        "-d",
                        "--remove-orphans",
                        "--force-recreate",
                    ),
                    prozessumgebung_fuer_konfiguration(startkonfiguration),
                ),
            ],
            self._projekt_pfad,
            timeout=600,
            parent=self,
        )
        self._start_dialog = dialog
        self._prozess_dialoge.append(dialog)
        dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
        self.container_bereich.aktions_button.setEnabled(False)
        self.ausgabe_bereich.setze_ausgabe(
            f"Compose-Stack wird neu gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

        def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
            self.container_bereich.aktions_button.setEnabled(True)
            if self._start_dialog is dialog:
                self._start_dialog = None

            if not erfolgreich:
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack konnte nicht neu gestartet werden."
                )
                return

            speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
            self._letzte_startkonfiguration = startkonfiguration
            self.aktualisiere_inhalt()
            self.ausgabe_bereich.setze_ausgabe(
                ausgabe
                or f"Compose-Stack neu gestartet: {', '.join(startkonfiguration.dienst_ids)}"
            )

        dialog.setze_abgeschlossen_callback(abgeschlossen)
        dialog.starten()
        dialog.open()

    def _stoppe_dienste(self) -> None:
        if self._letzte_startkonfiguration is not None:
            if self._start_dialog is not None and self._start_dialog.isVisible():
                self._start_dialog.raise_()
                self._start_dialog.activateWindow()
                return

            startkonfiguration = self._letzte_startkonfiguration
            dialog = PodmanProzessDialog(
                "Compose-Stack stoppen",
                podman_compose_argumente(
                    startkonfiguration,
                    "down",
                    "--remove-orphans",
                ),
                self._projekt_pfad,
                prozessumgebung_fuer_konfiguration(startkonfiguration),
                timeout=300,
                parent=self,
            )
            self._start_dialog = dialog
            self._prozess_dialoge.append(dialog)
            dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
            self.container_bereich.aktions_button.setEnabled(False)
            self.ausgabe_bereich.setze_ausgabe(
                f"Compose-Stack wird gestoppt: {', '.join(startkonfiguration.dienst_ids)}"
            )

            def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
                self.container_bereich.aktions_button.setEnabled(True)
                if self._start_dialog is dialog:
                    self._start_dialog = None

                if not erfolgreich:
                    self.ausgabe_bereich.setze_ausgabe(
                        ausgabe or "Compose-Stack konnte nicht gestoppt werden."
                    )
                    return

                loesche_startkonfiguration(self._compose_status_pfad)
                self._letzte_startkonfiguration = None
                self.aktualisiere_inhalt()
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Compose-Stack gestoppt und entfernt."
                )

            dialog.setze_abgeschlossen_callback(abgeschlossen)
            dialog.starten()
            dialog.open()
            return

        laufende_container = self._laufende_bekannte_container()
        if laufende_container:
            dialog = PodmanProzessDialog(
                "Bekannte Container stoppen",
                ["stop", *laufende_container],
                self._projekt_pfad,
                {},
                timeout=300,
                parent=self,
            )
            self._start_dialog = dialog
            self._prozess_dialoge.append(dialog)
            dialog.finished.connect(lambda _result: self._entferne_prozess_dialog(dialog))
            self.container_bereich.aktions_button.setEnabled(False)
            self.ausgabe_bereich.setze_ausgabe(
                f"Container werden gestoppt: {', '.join(laufende_container)}"
            )

            def abgeschlossen(erfolgreich: bool, ausgabe: str) -> None:
                self.container_bereich.aktions_button.setEnabled(True)
                if self._start_dialog is dialog:
                    self._start_dialog = None

                self.aktualisiere_inhalt()
                if erfolgreich:
                    self.ausgabe_bereich.setze_ausgabe(
                        ausgabe or f"stop: {', '.join(laufende_container)}"
                    )
                    return
                self.ausgabe_bereich.setze_ausgabe(
                    ausgabe or "Bekannte Container konnten nicht gestoppt werden."
                )

            dialog.setze_abgeschlossen_callback(abgeschlossen)
            dialog.starten()
            dialog.open()
            return

        self.ausgabe_bereich.setze_ausgabe(
            "Es wurden keine laufenden Container gefunden."
        )

    def _laufende_bekannte_container(self) -> list[str]:
        container_namen: list[str] = []
        for dienst in DIENSTE:
            status = self._container_status.get(dienst.dienst_id, {})
            container_name = str(status.get("container_name") or "")
            if not container_name or not bool(status.get("laeuft")):
                continue
            if container_name not in container_namen:
                container_namen.append(container_name)
        return container_namen

    def _status_nach_dienst(
        self,
        container_rohdaten: list[dict[str, Any]],
    ) -> dict[str, dict[str, object]]:
        container_index: dict[str, dict[str, Any]] = {}
        for container in container_rohdaten:
            for name in self._container_namen(container):
                container_index[name.lower()] = container

        status_nach_dienst: dict[str, dict[str, object]] = {}
        for dienst in DIENSTE:
            container = self._finde_container_fuer_dienst(dienst, container_index)
            status_nach_dienst[dienst.dienst_id] = self._formatierter_status(container)
        return status_nach_dienst

    def _finde_container_fuer_dienst(
        self,
        dienst: DienstDefinition,
        container_index: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        for kandidat in dienst.container_namen:
            kandidat_lower = kandidat.lower()
            if kandidat_lower in container_index:
                return container_index[kandidat_lower]

            for container_name, container in container_index.items():
                if container_name.startswith(f"{kandidat_lower}-"):
                    return container

        return None

    def _formatierter_status(self, container: dict[str, Any] | None) -> dict[str, object]:
        if not container:
            return {
                "container_name": None,
                "laeuft": False,
                "anzeige_status": "Nicht gefunden",
            }

        state = str(container.get("State") or "").lower()
        status = str(container.get("Status") or container.get("State") or "Unbekannt")
        return {
            "container_name": self._container_namen(container)[0] if self._container_namen(container) else None,
            "laeuft": state == "running" or status.lower().startswith("up"),
            "anzeige_status": status,
        }

    def _container_namen(self, container: dict[str, Any]) -> list[str]:
        namen = container.get("Names") or container.get("Name") or []
        if isinstance(namen, str):
            return [namen]
        if isinstance(namen, list):
            return [str(name) for name in namen if name]
        return []

    def _lade_status_und_volumen(self) -> dict[str, object]:
        container_rohdaten, container_fehler = lade_json_liste(
            self._projekt_pfad,
            ["ps", "-a"],
            timeout=8,
        )
        volumen_rohdaten, volumen_fehler = lade_json_liste(
            self._projekt_pfad,
            [
                "volume",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={PROJEKT_NAME}",
            ],
            timeout=8,
        )
        volumen_liste = [
            {
                "name": str(volumen.get("Name") or ""),
                "driver": str(volumen.get("Driver") or ""),
                "mountpoint": str(volumen.get("Mountpoint") or ""),
            }
            for volumen in volumen_rohdaten
        ]
        return {
            "container_rohdaten": container_rohdaten,
            "container_fehler": container_fehler,
            "volumen_liste": volumen_liste,
            "volumen_fehler": volumen_fehler,
        }

    def _status_und_volumen_geladen(self, ergebnis: object) -> None:
        if self._wird_beendet:
            return
        self._aktualisierung_laeuft = False
        if isinstance(ergebnis, HintergrundFehler):
            self._letzter_status_fehler = ergebnis.meldung
            self._container_status = self._status_nach_dienst([])
            self._aktualisiere_containerdarstellung()
            self.volumen_bereich.setze_volumen([], ergebnis.meldung)
        elif isinstance(ergebnis, dict):
            container_rohdaten = ergebnis.get("container_rohdaten")
            self._letzter_status_fehler = str(ergebnis.get("container_fehler") or "")
            self._container_status = self._status_nach_dienst(
                container_rohdaten if isinstance(container_rohdaten, list) else []
            )
            self._aktualisiere_containerdarstellung()

            volumen_liste = ergebnis.get("volumen_liste")
            self.volumen_bereich.setze_volumen(
                volumen_liste if isinstance(volumen_liste, list) else [],
                str(ergebnis.get("volumen_fehler") or ""),
            )

        self._aktualisiere_logs()
        if self._aktualisierung_angefordert:
            QTimer.singleShot(0, self.aktualisiere_inhalt)

    def _starte_log_aktualisierung(self) -> None:
        if self._wird_beendet:
            return
        if self._log_auftrag_laeuft:
            self._log_aktualisierung_angefordert = True
            return

        container_name = self._ausgewaehlter_container
        if not container_name:
            self._aktualisiere_logs()
            return

        self._log_auftrag_laeuft = True
        self._log_aktualisierung_angefordert = False
        self._log_anfrage_id += 1
        anfrage_id = self._log_anfrage_id
        projekt_pfad = self._projekt_pfad

        def lade_logs() -> dict[str, object]:
            ausgabe, fehler = fuehre_podman_kommando(
                projekt_pfad,
                ["logs", "--tail", "200", container_name],
                timeout=8,
            )
            return {
                "anfrage_id": anfrage_id,
                "container_name": container_name,
                "ausgabe": ausgabe,
                "fehler": fehler,
            }

        self._starte_hintergrundauftrag(lade_logs, self._logs_geladen)

    def _logs_geladen(self, ergebnis: object) -> None:
        if self._wird_beendet:
            return
        self._log_auftrag_laeuft = False
        if isinstance(ergebnis, HintergrundFehler):
            self.ausgabe_bereich.setze_ausgabe(ergebnis.meldung)
        elif isinstance(ergebnis, dict):
            if ergebnis.get("anfrage_id") == self._log_anfrage_id and (
                ergebnis.get("container_name") == self._ausgewaehlter_container
            ):
                fehler = str(ergebnis.get("fehler") or "")
                ausgabe = str(ergebnis.get("ausgabe") or "")
                self.ausgabe_bereich.setze_ausgabe(
                    fehler or ausgabe or "Keine Log-Ausgabe vorhanden."
                )

        if self._log_aktualisierung_angefordert:
            self._log_timer.start()

    def _starte_hintergrundauftrag(
        self,
        funktion,
        abgeschlossen,
    ) -> None:
        if self._wird_beendet:
            return
        thread = QThread(self)
        worker = HintergrundWorker(funktion)
        worker.moveToThread(thread)
        thread.started.connect(worker.ausfuehren)
        worker.fertig.connect(abgeschlossen)
        worker.fertig.connect(thread.quit)
        worker.fertig.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._entferne_hintergrund_thread(thread))
        thread.finished.connect(thread.deleteLater)
        thread._worker = worker
        self._hintergrund_threads.append(thread)
        thread.start()

    def _entferne_hintergrund_thread(self, thread: QThread) -> None:
        if thread in self._hintergrund_threads:
            self._hintergrund_threads.remove(thread)

    def _beende_hintergrund_threads(self) -> None:
        self._wird_beendet = True
        self._log_timer.stop()
        for thread in list(self._hintergrund_threads):
            thread.quit()
            thread.wait(17000)
            self._entferne_hintergrund_thread(thread)
