"""InteractiveController — keyboard input handling for runtime control."""
from __future__ import annotations

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
    """Captures keyboard input and dispatches runtime commands.

    Adjustments are staged (pending) until Enter is pressed, then applied
    with a single ffmpeg restart. Press 'r' to cancel pending changes.
    """

    def __init__(self, manager: StreamManager):
        self._manager = manager
        self._running = False
        self._original_settings: list | None = None

        # Pending state — accumulated adjustments not yet committed
        self._pending_offset_delta: int = 0
        self._pending_video: str | None = None
        self._pending_audio: str | None = None

    def run(self) -> None:
        """Start the interactive keyboard loop. Blocks until shutdown() is called
        or 'q' is pressed."""
        self._running = True
        self._setup_terminal()

        print("Interactive mode active. Press 'h' for help, 'q' to quit.")
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
        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return
        char2 = sys.stdin.read(1)
        if char2 != "[":
            return

        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return
        char3 = sys.stdin.read(1)

        if char3 == "A":  # Up arrow
            return
        elif char3 == "B":  # Down arrow
            return
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
            "\x03": self._force_quit,   # Ctrl-C (always quits)
            "\x04": self._force_quit,   # Ctrl-D (always quits)
            "\r": self._commit,         # Enter
            "\n": self._commit,         # Enter
            "q": self._do_quit,
            "Q": self._do_quit,
            "v": self._toggle_video,
            "V": self._toggle_video,
            "a": self._toggle_audio,
            "A": self._toggle_audio,
            "r": self._reset_pending,
            "R": self._reset_pending,
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

    # ── pending state management ────────────────────────────────

    def _has_pending(self) -> bool:
        """Return True if there are uncommitted changes."""
        return (self._pending_offset_delta != 0
                or self._pending_video is not None
                or self._pending_audio is not None)

    def _commit(self) -> None:
        """Apply all pending adjustments with a single restart."""
        if not self._has_pending():
            print("[no pending changes to commit]")
            return

        # Collect what changed for the log message
        changes = []

        if self._pending_offset_delta != 0:
            old = self._manager.offset_ms
            new = old + self._pending_offset_delta
            self._manager.offset_ms = new
            changes.append(f"offset {format_offset(old)} → {format_offset(new)}")
            logger.info("Committed offset: %s → %s (Δ %+dms)",
                        format_offset(old), format_offset(new),
                        self._pending_offset_delta)

        if self._pending_video is not None:
            old = self._manager.video
            self._manager.video = self._pending_video
            changes.append(f"video {old} → {self._pending_video}")
            logger.info("Committed video source: %s → %s",
                        old, self._pending_video)

        if self._pending_audio is not None:
            old = self._manager.audio
            self._manager.audio = self._pending_audio
            changes.append(f"audio {old} → {self._pending_audio}")
            logger.info("Committed audio source: %s → %s",
                        old, self._pending_audio)

        print(f">>> COMMITTED: {', '.join(changes)}")
        self._clear_pending()
        self._manager.restart()

    def _clear_pending(self) -> None:
        """Clear all pending state."""
        self._pending_offset_delta = 0
        self._pending_video = None
        self._pending_audio = None

    def _reset_pending(self) -> None:
        """Cancel all pending adjustments."""
        if not self._has_pending():
            print("[no pending changes to cancel]")
            return
        print(">>> CANCELLED pending changes")
        self._clear_pending()

    def _show_pending(self) -> None:
        """Display current pending adjustments on stdout."""
        parts = []
        if self._pending_offset_delta != 0:
            effective = self._manager.offset_ms + self._pending_offset_delta
            delta_str = format_offset(self._pending_offset_delta)
            if self._pending_offset_delta > 0:
                delta_str = f"+{delta_str}"
            parts.append(f"offset → {format_offset(effective)} (Δ {delta_str})")
        if self._pending_video is not None:
            parts.append(f"video → {self._pending_video}")
        if self._pending_audio is not None:
            parts.append(f"audio → {self._pending_audio}")

        if parts:
            print(f"[PENDING] {', '.join(parts)}  |  Enter=commit  r=cancel")

    # ── adjustments (stage only, no restart) ────────────────────

    def _adjust_offset(self, delta_ms: int) -> None:
        """Accumulate an offset delta (no restart until commit)."""
        self._pending_offset_delta += delta_ms
        self._show_pending()

    def _toggle_video(self) -> None:
        """Toggle pending video source."""
        current = self._pending_video if self._pending_video is not None else self._manager.video
        self._pending_video = "b" if current == "a" else "a"
        self._show_pending()

    def _toggle_audio(self) -> None:
        """Toggle pending audio source."""
        current = self._pending_audio if self._pending_audio is not None else self._manager.audio
        self._pending_audio = "b" if current == "a" else "a"
        self._show_pending()

    # ── display ─────────────────────────────────────────────────

    def _print_status(self) -> None:
        """Print current runtime status."""
        uptime_s = (time.monotonic() - self._manager.start_time
                    if self._manager.start_time else 0)
        pending_info = ""
        if self._has_pending():
            pending_info = " [PENDING]"
        print(
            f"STATUS | offset={format_offset(self._manager.offset_ms)} "
            f"| video={self._manager.video} | audio={self._manager.audio} "
            f"| ffmpeg={'running' if self._manager.is_running() else 'stopped'} "
            f"| uptime={int(uptime_s)}s | restarts={self._manager.restart_count}"
            f"{pending_info}"
        )
        # Also log to file
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
        print(
            f"HOTKEYS | ← → : offset ±{OFFSET_FINE_MS}ms "
            f"| Shift+←→ : ±{OFFSET_COARSE_MS}ms "
            f"| [ ] : ±{OFFSET_COARSE_MS}ms "
            f"| +/- : ±{OFFSET_FINE_MS}ms"
        )
        print("          v: toggle video | a: toggle audio | s: status")
        print("          Enter: commit | r: cancel | q: quit | Ctrl+C: force quit")

    def _do_quit(self) -> None:
        """Quit if no pending changes; warn otherwise."""
        if self._has_pending():
            print(">>> You have uncommitted changes. Press Enter to commit, r to cancel, or Ctrl+C to force quit.")
            return
        print("Shutting down...")
        self.shutdown()

    def _force_quit(self) -> None:
        """Force quit — discard pending changes and exit immediately."""
        if self._has_pending():
            print(">>> Discarding pending changes...")
            self._clear_pending()
        print("Shutting down...")
        self.shutdown()
