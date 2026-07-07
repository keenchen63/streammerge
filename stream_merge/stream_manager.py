"""StreamManager — manages ffmpeg subprocess lifecycle."""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import TextIO

from stream_merge.command import build_ffmpeg_command

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_RETRIES = 5
RESTART_DELAY_SEC = 2.0
STALE_SEGMENT_THRESHOLD_SEC = 15.0


class StreamManager:
    """Manages the ffmpeg subprocess that merges two HLS streams."""

    def __init__(
        self,
        stream_a: str,
        stream_b: str,
        video: str,
        audio: str,
        offset_ms: int,
        output_dir: str,
        low_latency: bool = True,
    ):
        self.stream_a = stream_a
        self.stream_b = stream_b
        self.video = video
        self.audio = audio
        self.offset_ms = offset_ms
        self.output_dir = output_dir
        self.low_latency = low_latency

        self._process: subprocess.Popen | None = None
        self._log_file: TextIO | None = None
        self.start_time: float | None = None
        self.restart_count: int = 0
        self._consecutive_failures: int = 0
        self._last_segment_time: float = 0.0

    # ── public API ──────────────────────────────────────────────

    def start(self) -> None:
        """Launch the ffmpeg subprocess."""
        self._ensure_output_dir()
        self._cleanup_stale_files()
        self._open_log()
        self._launch()
        self.start_time = time.monotonic()

    def stop(self) -> None:
        """Terminate ffmpeg gracefully, then forcefully if needed."""
        if self._process is None:
            return

        proc = self._process
        self._process = None

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
                logger.info("ffmpeg terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("ffmpeg did not terminate, sending SIGKILL")
                proc.kill()
                proc.wait(timeout=5)
        except ProcessLookupError:
            pass  # Already exited
        finally:
            self._close_log()

    def restart(self) -> None:
        """Stop and restart ffmpeg with current configuration."""
        logger.info("Restarting ffmpeg (offset=%dms, video=%s, audio=%s)",
                    self.offset_ms, self.video, self.audio)
        self.stop()
        time.sleep(0.5)  # Brief cooldown for file handles
        self.start()
        self.restart_count += 1

    def update_offset(self, ms: int) -> None:
        """Update audio offset and restart."""
        self.offset_ms = ms
        self.restart()

    def update_source(self, video: str | None = None, audio: str | None = None) -> None:
        """Update track source selection and restart."""
        if video is not None:
            self.video = video
        if audio is not None:
            self.audio = audio
        self.restart()

    def is_running(self) -> bool:
        """Return True if the ffmpeg process is currently alive."""
        return self._process is not None and self._process.poll() is None

    def had_consecutive_failures(self) -> bool:
        """Return True if we've exceeded the max consecutive crash limit."""
        return self._consecutive_failures >= MAX_CONSECUTIVE_RETRIES

    # ── internal ────────────────────────────────────────────────

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _cleanup_stale_files(self) -> None:
        """Remove stale .ts and .m3u8 files from the output directory on startup."""
        out = Path(self.output_dir)
        if not out.exists():
            return
        cleaned = 0
        for f in out.iterdir():
            if f.suffix in (".ts", ".m3u8"):
                try:
                    f.unlink()
                    cleaned += 1
                except OSError:
                    pass
        if cleaned:
            logger.info("Cleaned up %d stale segment file(s) from %s",
                        cleaned, self.output_dir)

    def _open_log(self) -> None:
        """Open the ffmpeg stderr log file."""
        log_path = os.path.join(self.output_dir, "ffmpeg.log")
        self._log_file = open(log_path, "a")

    def _close_log(self) -> None:
        """Close the ffmpeg stderr log file."""
        if self._log_file:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def _launch(self) -> None:
        """Build the command and spawn the ffmpeg subprocess."""
        cmd = build_ffmpeg_command(
            stream_a=self.stream_a,
            stream_b=self.stream_b,
            video=self.video,
            audio=self.audio,
            offset_ms=self.offset_ms,
            output_dir=self.output_dir,
            low_latency=self.low_latency,
        )
        logger.debug("Launching: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=self._log_file,
        )

    def _handle_crash(self) -> bool:
        """Handle ffmpeg process exit. Returns True if we should restart."""
        exit_code = self._process.returncode if self._process else -1
        logger.warning("ffmpeg exited with code %d", exit_code)

        if exit_code == 0 or exit_code == -15:  # SIGTERM is intentional
            self._consecutive_failures = 0
            return False

        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_RETRIES:
            logger.error(
                "ffmpeg crashed %d times consecutively — giving up",
                self._consecutive_failures,
            )
            return False

        logger.info(
            "Restarting ffmpeg in %.1fs (attempt %d/%d)...",
            RESTART_DELAY_SEC,
            self._consecutive_failures,
            MAX_CONSECUTIVE_RETRIES,
        )
        time.sleep(RESTART_DELAY_SEC)
        self._close_log()
        self._open_log()
        self._launch()
        self.start_time = time.monotonic()
        self.restart_count += 1
        self._consecutive_failures = 0
        return True
