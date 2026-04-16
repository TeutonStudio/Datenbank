from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from Kern.compose.env import Umgebungsvariablen
from Schnittstelle.verwaltung.compose.container_widget import DienstDefinition
from Schnittstelle.verwaltung.compose_widget import ComposeWidget

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
]


class VerwaltungFenster(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.projekt_pfad = Path(__file__).resolve().parents[2]
        self._env_pfad = self.projekt_pfad / ".env"
        alter_env_pfad = self.projekt_pfad / "Schnittstelle" / ".env"
        if not self._env_pfad.exists() and alter_env_pfad.exists():
            self._env_pfad = alter_env_pfad
        self._env_cache_pfad = self._env_pfad.with_suffix(".draft.json")
        self._umgebungsvariablen = Umgebungsvariablen(
            self._env_pfad,
            self._env_cache_pfad,
        )
        self._container_status: dict[str, dict[str, object]] = {}
        self._ausgewaehlter_container: str | None = None
        self._ausgewaehlter_dienst = "Kein Dienst ausgewählt"
        self._letzter_status_fehler = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.compose = ComposeWidget(self, self._umgebungsvariablen)
        layout.addWidget(self.compose)


        self.aktualisierungs_timer = QTimer(self)
        self.aktualisierungs_timer.setInterval(5000)
        self.aktualisierungs_timer.timeout.connect(self.compose.aktualisiere_inhalt)
        self.aktualisierungs_timer.start()

        self.compose.aktualisiere_inhalt()
