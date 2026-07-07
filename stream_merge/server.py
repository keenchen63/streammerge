"""HLSServer — lightweight HTTP server for HLS output directory."""

import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger(__name__)


class _CORSRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with CORS headers for HLS playback."""

    def __init__(self, *args, directory: str, **kwargs):
        self.directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        logger.debug("HTTP %s", format % args)


class HLSServer:
    """Lightweight HTTP server to expose the HLS output directory over LAN."""

    def __init__(self, output_dir: str, port: int):
        self.output_dir = str(Path(output_dir).resolve())
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the HTTP server in a background daemon thread."""
        if self.port == 0:
            logger.info("HTTP server disabled (port=0)")
            return

        def handler(*args, **kwargs):
            return _CORSRequestHandler(*args, directory=self.output_dir, **kwargs)

        self._server = HTTPServer(("0.0.0.0", self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="hls-http-server",
            daemon=True,
        )
        self._thread.start()
        logger.info("HLS HTTP server listening on http://0.0.0.0:%d", self.port)

    def stop(self) -> None:
        """Shutdown the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            logger.info("HLS HTTP server stopped")

    def is_running(self) -> bool:
        """Return True if the HTTP server is currently running."""
        return self._server is not None
