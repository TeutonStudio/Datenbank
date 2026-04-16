from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView

# TODO Websiten auth einbauen


class StilleWebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        return


class ProgrammSeite(QWebEngineView):
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = QUrl(url)
        self._geladen = False
        self.setPage(StilleWebEnginePage(self))

    def lade_wenn_noetig(self) -> None:
        if self._geladen:
            return
        self._geladen = True
        self.setUrl(self._url)
