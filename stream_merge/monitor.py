"""StatusMonitor — health checks, logging, and segment cleanup sweep."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from stream_merge.offset import format_offset
from stream_merge.stream_manager import StreamManager

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SEC = 60.0
STATUS_LOG_INTERVAL_SEC = 30.0
STALE_SEGMENT_THRESHOLD_SEC = 15.0


class StatusMonitor:
    """Background monitor for ffmpeg health and output segment hygiene."""

    def __init__(self, manager: StreamManager, output_dir: str):
        self._manager = manager
        self._output_dir = Path(output_dir)
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_status_log = 0.0
        self._last_sweep = 0.0

    def start(self) -> None:
        """Start monitoring in a background daemon thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="status-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("StatusMonitor started")

    def stop(self) -> None:
        """Stop the monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("StatusMonitor stopped")

    def run_once(self) -> None:
        """Perform a single health check + sweep cycle (for testing)."""
        self._check_ffmpeg_health()
        self._sweep_segments()
        self._log_status()

    # ── internal ────────────────────────────────────────────────

    def _loop(self) -> None:
        """Main monitoring loop — runs in background thread."""
        while self._running:
            try:
                self._check_ffmpeg_health()
                self._maybe_sweep()
                self._maybe_log_status()
            except Exception:
                logger.exception("Monitor error")
            time.sleep(1.0)

    def _check_ffmpeg_health(self) -> None:
        """Check if ffmpeg process is alive; trigger restart if crashed."""
        if self._manager.is_running():
            return
        if self._manager.had_consecutive_failures():
            return  # Already given up
        logger.warning("ffmpeg process not running — attempting restart")
        self._manager._handle_crash()

    def _maybe_sweep(self) -> None:
        """Run segment sweep if enough time has passed."""
        now = time.monotonic()
        if now - self._last_sweep >= SWEEP_INTERVAL_SEC:
            self._sweep_segments()
            self._last_sweep = now

    def _sweep_segments(self) -> None:
        """Delete excess .ts files beyond hls_list_size * 2."""
        if not self._output_dir.exists():
            return

        ts_files = sorted(
            self._output_dir.glob("*.ts"),
            key=lambda f: f.stat().st_mtime,
        )
        max_files = 10 * 2  # hls_list_size * 2
        if len(ts_files) <= max_files:
            return

        excess = len(ts_files) - max_files
        logger.warning(
            "Segment sweep: %d .ts files found (limit %d), removing %d oldest",
            len(ts_files), max_files, excess,
        )
        for f in ts_files[:excess]:
            try:
                f.unlink()
            except OSError:
                pass

    def _maybe_log_status(self) -> None:
        """Log condensed status every STATUS_LOG_INTERVAL_SEC."""
        now = time.monotonic()
        if now - self._last_status_log >= STATUS_LOG_INTERVAL_SEC:
            self._log_status()
            self._last_status_log = now

    def _log_status(self) -> None:
        """Log a one-line status summary."""
        uptime_s = (time.monotonic() - self._manager.start_time
                    if self._manager.start_time else 0)
        ts_count = len(list(self._output_dir.glob("*.ts"))) if self._output_dir.exists() else 0
        logger.info(
            "[HEALTH] offset=%s video=%s audio=%s ffmpeg=%s uptime=%ds "
            "restarts=%d segments=%d",
            format_offset(self._manager.offset_ms),
            self._manager.video,
            self._manager.audio,
            "running" if self._manager.is_running() else "stopped",
            int(uptime_s),
            self._manager.restart_count,
            ts_count,
        )

    def _check_stale_segments(self) -> bool:
        """Check if new segments are being produced. Returns True if healthy."""
        if not self._output_dir.exists():
            return False
        ts_files = sorted(
            self._output_dir.glob("*.ts"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not ts_files:
            return False  # No segments yet
        latest_mtime = ts_files[0].stat().st_mtime
        age = time.time() - latest_mtime
        return age < STALE_SEGMENT_THRESHOLD_SEC
