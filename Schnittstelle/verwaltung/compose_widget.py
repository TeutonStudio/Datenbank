import json
import subprocess
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter

from Kern.podman import lade_startkonfiguration, speichere_ausgewaehlte_dienste, \
    startkonfigurationen_unterscheiden_sich, PodmanComposeStartKonfiguration, baue_startkonfiguration, \
    podman_compose_argumente, prozessumgebung_fuer_konfiguration, speichere_startkonfiguration, \
    loesche_startkonfiguration
from Schnittstelle.verwaltung.compose.ausgabe_widget import AusgabeBereich
from Schnittstelle.verwaltung.compose.container_widget import ContainerBereich, DienstDefinition
from Schnittstelle.verwaltung.compose.volumen_widget import VolumenBereich
from Schnittstelle.verwaltung.einstellungen_dialog import EinstellungenDialog

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
]

# TODO vereinfachen
# TODO einen Selektor definieren, der übergreifend eines aus entweder container oder volumen auswählt (oder nichts). Dieser Selektor definiert welches log im ausgabe dargestellt wird (bei nichts ist es das des gesamten container)
class ComposeWidget(QSplitter):
    def __init__(self,parent):
        super().__init__(Qt.Orientation.Vertical,parent)
        self._projekt_pfad = parent.projekt_pfad
        self._compose_status_pfad = self._projekt_pfad / ".compose.state.json"
        self._letzte_startkonfiguration = lade_startkonfiguration(
            self._compose_status_pfad
        )

        self.container_bereich = ContainerBereich(DIENSTE, self)
        self.volumen_bereich = VolumenBereich(parent)
        self.ausgabe_bereich = AusgabeBereich(parent)

        # if self._letzte_dienstauswahl is not None:
        #     self.container_bereich.setze_auswahl(
        #         self._letzte_dienstauswahl,
        #         als_manuelle_auswahl=True,
        #     )

        unterer_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        unterer_splitter.addWidget(self.volumen_bereich)
        unterer_splitter.addWidget(self.ausgabe_bereich)
        unterer_splitter.setStretchFactor(0, 1)
        unterer_splitter.setStretchFactor(1, 2)

        self.addWidget(self.container_bereich)
        self.addWidget(unterer_splitter)

        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 2)

        self.volumen_bereich.aktualisieren_angefragt.connect(self._aktualisiere_volumen)
        self.ausgabe_bereich.aktualisieren_angefragt.connect(self._aktualisiere_logs)

        self.container_bereich.container_gewaehlt.connect(self._setze_ausgewaehlten_container)
        self.container_bereich.dienste_schalten.connect(self._schalte_dienste)
        self.container_bereich.auswahl_geaendert.connect(self._bei_auswahl_geaendert)
        self.container_bereich.aktualisieren_angefragt.connect(self.aktualisiere_inhalt)
        self.container_bereich.einstellungen_angefragt.connect(self._oeffne_einstellungen)
        self.volumen_bereich.aktualisieren_angefragt.connect(self._aktualisiere_volumen)
        self.ausgabe_bereich.aktualisieren_angefragt.connect(self._aktualisiere_logs)

    def aktualisiere_inhalt(self) -> None:
        self._aktualisiere_container()
        self._aktualisiere_volumen()
        self._aktualisiere_logs()

    def _aktualisiere_container(self) -> None:
        container_rohdaten, fehler = self._lade_json_liste(["ps", "-a"])
        self._letzter_status_fehler = fehler
        self._container_status = self._status_nach_dienst(container_rohdaten)
        self._aktualisiere_containerdarstellung()

    def _aktualisiere_volumen(self) -> None:
        volumen_rohdaten, fehler = self._lade_json_liste(["volume", "ls"])
        volumen_liste = []
        for volumen in volumen_rohdaten:
            volumen_liste.append(
                {
                    "name": str(volumen.get("Name") or ""),
                    "driver": str(volumen.get("Driver") or ""),
                    "mountpoint": str(volumen.get("Mountpoint") or ""),
                }
            )
        self.volumen_bereich.setze_volumen(volumen_liste, fehler)

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

        ausgabe, fehler = self._fuehre_podman_kommando(
            ["logs", "--tail", "200", self._ausgewaehlter_container]
        )
        if fehler:
            self.ausgabe_bereich.setze_ausgabe(fehler)
            return
        self.ausgabe_bereich.setze_ausgabe(ausgabe or "Keine Log-Ausgabe vorhanden.")

    def _setze_ausgewaehlten_container(
        self,
        container_name: str | None,
        dienst_titel: str,
    ) -> None:
        self._ausgewaehlter_container = container_name
        self._ausgewaehlter_dienst = dienst_titel
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
        self.container_bereich.setze_status(
            self._container_status,
            self._letzter_status_fehler,
            konfiguration_geaendert=self._konfiguration_ist_geaendert(),
        )

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
                f"Einstellungen gespeichert: {self._env_pfad.name}"
            )
            self._aktualisiere_containerdarstellung()

    def _lade_json_liste(self, basis_befehl: list[str]) -> tuple[list[dict[str, any]], str]:
        daten, fehler = self._fuehre_podman_kommando([*basis_befehl, "--format", "json"])
        if daten:
            try:
                geparst = json.loads(daten)
                if isinstance(geparst, list):
                    return geparst, ""
                if isinstance(geparst, dict):
                    return [geparst], ""
            except json.JSONDecodeError:
                pass

        daten, fehler = self._fuehre_podman_kommando([*basis_befehl, "--format", "{{json .}}"])
        if not daten:
            return [], fehler

        zeilen = []
        for zeile in daten.splitlines():
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                zeilen.append(json.loads(zeile))
            except json.JSONDecodeError:
                continue
        return zeilen, fehler if not zeilen else ""

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
        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        ausgabe, fehler = self._fuehre_podman_kommando(
            podman_compose_argumente(
                startkonfiguration,
                "up",
                "-d",
                "--remove-orphans",
            ),
            umgebung=prozessumgebung_fuer_konfiguration(startkonfiguration),
            timeout=600,
        )
        if fehler:
            self.ausgabe_bereich.setze_ausgabe(fehler)
            return

        speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
        self._letzte_startkonfiguration = startkonfiguration
        self.aktualisiere_inhalt()
        self.ausgabe_bereich.setze_ausgabe(
            ausgabe or f"Compose-Stack gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

    def _neustarte_dienste(self, dienst_ids: list[str]) -> None:
        try:
            startkonfiguration = baue_startkonfiguration(
                dienst_ids,
                self._umgebungsvariablen,
            )
        except ValueError as fehler:
            self.ausgabe_bereich.setze_ausgabe(str(fehler))
            return

        if self._letzte_startkonfiguration is not None:
            _, fehler = self._fuehre_podman_kommando(
                podman_compose_argumente(
                    self._letzte_startkonfiguration,
                    "down",
                    "--remove-orphans",
                ),
                umgebung=prozessumgebung_fuer_konfiguration(
                    self._letzte_startkonfiguration
                ),
                timeout=300,
            )
            if fehler:
                self.ausgabe_bereich.setze_ausgabe(fehler)
                return
        else:
            bearbeitet, fehler_liste = self._stoppe_bekannte_container(entfernen=True)
            if fehler_liste:
                self.ausgabe_bereich.setze_ausgabe("\n\n".join(fehler_liste))
                return
            if not bearbeitet and self._irgendetwas_laeuft():
                self.ausgabe_bereich.setze_ausgabe(
                    "Laufende Container konnten vor dem Neustart nicht eindeutig zugeordnet werden."
                )
                return

        ausgabe, fehler = self._fuehre_podman_kommando(
            podman_compose_argumente(
                startkonfiguration,
                "up",
                "-d",
                "--remove-orphans",
                "--force-recreate",
            ),
            umgebung=prozessumgebung_fuer_konfiguration(startkonfiguration),
            timeout=600,
        )
        if fehler:
            self.ausgabe_bereich.setze_ausgabe(fehler)
            return

        speichere_startkonfiguration(self._compose_status_pfad, startkonfiguration)
        self._letzte_startkonfiguration = startkonfiguration
        self.aktualisiere_inhalt()
        self.ausgabe_bereich.setze_ausgabe(
            ausgabe
            or f"Compose-Stack neu gestartet: {', '.join(startkonfiguration.dienst_ids)}"
        )

    def _stoppe_dienste(self) -> None:
        if self._letzte_startkonfiguration is not None:
            ausgabe, fehler = self._fuehre_podman_kommando(
                podman_compose_argumente(
                    self._letzte_startkonfiguration,
                    "down",
                    "--remove-orphans",
                ),
                umgebung=prozessumgebung_fuer_konfiguration(
                    self._letzte_startkonfiguration
                ),
                timeout=300,
            )
            if fehler:
                self.ausgabe_bereich.setze_ausgabe(fehler)
                return

            loesche_startkonfiguration(self._compose_status_pfad)
            self._letzte_startkonfiguration = None
            self.aktualisiere_inhalt()
            self.ausgabe_bereich.setze_ausgabe(
                ausgabe or "Compose-Stack gestoppt und entfernt."
            )
            return

        bearbeitet, fehler_liste = self._stoppe_bekannte_container()
        self.aktualisiere_inhalt()

        if fehler_liste:
            self.ausgabe_bereich.setze_ausgabe("\n\n".join(fehler_liste))
            return

        if bearbeitet:
            self.ausgabe_bereich.setze_ausgabe(
                f"stop: {', '.join(bearbeitet)}"
            )
            return

        self.ausgabe_bereich.setze_ausgabe(
            "Es wurden keine laufenden Container gefunden."
        )

    def _stoppe_bekannte_container(
        self,
        *,
        entfernen: bool = False,
    ) -> tuple[list[str], list[str]]:
        bearbeitet: list[str] = []
        fehler_liste: list[str] = []
        befehl = "rm" if entfernen else "stop"

        for dienst in DIENSTE:
            status = self._container_status.get(dienst.dienst_id, {})
            container_name = str(status.get("container_name") or "")
            if not container_name:
                continue
            if not entfernen and not bool(status.get("laeuft")):
                continue

            argumente = [befehl, container_name]
            if entfernen:
                argumente.insert(1, "-f")

            _, fehler = self._fuehre_podman_kommando(argumente, timeout=120)
            if fehler:
                fehler_liste.append(f"{container_name}: {fehler}")
                continue
            bearbeitet.append(container_name)

        return bearbeitet, fehler_liste

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

    def _fuehre_podman_kommando(
        self,
        argumente: list[str],
        *,
        umgebung: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> tuple[str, str]:
        try:
            ergebnis = subprocess.run(
                ["podman", *argumente],
                cwd=self._projekt_pfad,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=umgebung,
            )
        except FileNotFoundError:
            return "", "Podman wurde nicht gefunden. Installation und Runtime folgen im nächsten Schritt."
        except subprocess.TimeoutExpired:
            return "", "Die Podman-Abfrage hat das Zeitlimit überschritten."

        stdout = ergebnis.stdout.strip()
        stderr = ergebnis.stderr.strip()
        if ergebnis.returncode != 0:
            return "", stderr or stdout or "Die Podman-Abfrage ist fehlgeschlagen."
        return stdout, ""
