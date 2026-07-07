"""InteractiveController — keyboard input handling for runtime control."""

import logging
import select
import sys
import termios
import time
import tty
from typing import Callable

from stream_merge.offset import format_offset
from stream_merge.stream_manager import StreamManager

logger = logging.getLogger(__name__)

OFFSET_FINE_MS = 50
OFFSET_COARSE_MS = 500


class InteractiveController:
    """Captures keyboard input and dispatches runtime commands."""

    def __init__(self, manager: StreamManager):
        self._manager = manager
        self._running = False
        self._original_settings: list | None = None

    def run(self) -> None:
        """Start the interactive keyboard loop. Blocks until shutdown() is called
        or 'q' is pressed."""
        self._running = True
        self._setup_terminal()

        logger.info("Interactive mode active. Press 'h' for help, 'q' to quit.")
        self._print_help()

        try:
            while self._running:
                if select.select([sys.stdin], [], [], 0.5)[0]:
                    char = sys.stdin.read(1)
                    if char:
                        self._dispatch(char)
                        # Handle multi-char escape sequences
                        if char == "\x1b":
                            self._handle_escape_sequence()
                time.sleep(0.01)
        finally:
            self._restore_terminal()

    def shutdown(self) -> None:
        """Signal the controller to exit its run loop."""
        self._running = False

    # ── internal ────────────────────────────────────────────────

    def _setup_terminal(self) -> None:
        """Put terminal in raw mode for single-key reads."""
        fd = sys.stdin.fileno()
        self._original_settings = termios.tcgetattr(fd)
        tty.setraw(fd)

    def _restore_terminal(self) -> None:
        """Restore terminal to original settings."""
        if self._original_settings:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN,
                                  self._original_settings)
            except termios.error:
                pass

    def _handle_escape_sequence(self) -> None:
        """Handle arrow keys and other escape sequences."""
        # Arrow keys send: \x1b [ A/B/C/D
        # Shift+arrow sends \x1b [ 1 ; 2 A/B/C/D
        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return
        char2 = sys.stdin.read(1)
        if char2 != "[":
            return

        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return
        char3 = sys.stdin.read(1)

        if char3 == "A":  # Up arrow
            return  # Not used
        elif char3 == "B":  # Down arrow
            return  # Not used
        elif char3 == "C":  # Right arrow
            self._adjust_offset(OFFSET_FINE_MS)
        elif char3 == "D":  # Left arrow
            self._adjust_offset(-OFFSET_FINE_MS)
        elif char3 in ("1", "2") and select.select([sys.stdin], [], [], 0.05)[0]:
            # Shift+arrow: \x1b [ 1 ; 2 A/B/C/D
            char4 = sys.stdin.read(1)
            if char4 == ";":
                char5 = sys.stdin.read(1)
                if char5 == "2":
                    char6 = sys.stdin.read(1)
                    if char6 == "C":
                        self._adjust_offset(OFFSET_COARSE_MS)
                    elif char6 == "D":
                        self._adjust_offset(-OFFSET_COARSE_MS)

    def _dispatch(self, char: str) -> None:
        """Dispatch a single key press to the appropriate action."""
        actions: dict[str, Callable[[], None]] = {
            "\x03": self._do_quit,   # Ctrl-C
            "\x04": self._do_quit,   # Ctrl-D
            "q": self._do_quit,
            "Q": self._do_quit,
            "v": self._toggle_video,
            "V": self._toggle_video,
            "a": self._toggle_audio,
            "A": self._toggle_audio,
            "s": self._print_status,
            "S": self._print_status,
            "h": self._print_help,
            "H": self._print_help,
            "+": lambda: self._adjust_offset(OFFSET_FINE_MS),
            "=": lambda: self._adjust_offset(OFFSET_FINE_MS),
            "-": lambda: self._adjust_offset(-OFFSET_FINE_MS),
            "]": lambda: self._adjust_offset(OFFSET_COARSE_MS),
            "[": lambda: self._adjust_offset(-OFFSET_COARSE_MS),
        }
        action = actions.get(char)
        if action:
            action()

    def _adjust_offset(self, delta_ms: int) -> None:
        """Adjust the audio offset by a delta and restart ffmpeg."""
        new_offset = self._manager.offset_ms + delta_ms
        logger.info("Offset: %s → %s (Δ %+dms)",
                    format_offset(self._manager.offset_ms),
                    format_offset(new_offset),
                    delta_ms)
        self._manager.update_offset(new_offset)

    def _toggle_video(self) -> None:
        """Toggle video source between a and b."""
        new = "b" if self._manager.video == "a" else "a"
        logger.info("Video source: %s → %s", self._manager.video, new)
        self._manager.update_source(video=new)

    def _toggle_audio(self) -> None:
        """Toggle audio source between a and b."""
        new = "b" if self._manager.audio == "a" else "a"
        logger.info("Audio source: %s → %s", self._manager.audio, new)
        self._manager.update_source(audio=new)

    def _print_status(self) -> None:
        """Print current runtime status."""
        uptime_s = (time.monotonic() - self._manager.start_time
                    if self._manager.start_time else 0)
        logger.info(
            "STATUS | offset=%s | video=%s | audio=%s | ffmpeg=%s | "
            "uptime=%ds | restarts=%d",
            format_offset(self._manager.offset_ms),
            self._manager.video,
            self._manager.audio,
            "running" if self._manager.is_running() else "stopped",
            int(uptime_s),
            self._manager.restart_count,
        )

    def _print_help(self) -> None:
        """Print hotkey reference."""
        logger.info(
            "HOTKEYS | ← → : offset ±%dms | Shift+←→ : ±%dms | "
            "[ ] : ±%dms | +/- : ±%dms | "
            "v: toggle video | a: toggle audio | s: status | q: quit",
            OFFSET_FINE_MS, OFFSET_COARSE_MS,
            OFFSET_COARSE_MS, OFFSET_FINE_MS,
        )

    def _do_quit(self) -> None:
        """Quit the interactive controller."""
        logger.info("Shutting down...")
        self.shutdown()
