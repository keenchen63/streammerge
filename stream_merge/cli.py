"""CLI argument parsing and entry point for stream_merge."""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

OFFSET_PATTERN = re.compile(r'^[+-]?\d+(\.\d+)?(ms|s)$')

# Defaults used by both argparse and interactive prompt
DEFAULTS = {
    "video": "a",
    "audio": "a",
    "offset": "0ms",
    "output_dir": "/tmp/streammerge",
    "port": 38080,
    "low_latency": "true",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and return a namespace."""
    parser = argparse.ArgumentParser(
        prog="streammerge",
        description="Merge video and audio tracks from two HLS live streams.",
    )
    parser.add_argument(
        "-i", "--interactive", action="store_true",
        help="Enter interactive prompt mode to input parameters step by step",
    )
    parser.add_argument(
        "--stream-a",
        help="First HLS input stream URL (.m3u8)",
    )
    parser.add_argument(
        "--stream-b",
        help="Second HLS input stream URL (.m3u8)",
    )
    parser.add_argument(
        "--video", choices=["a", "b"], default=DEFAULTS["video"],
        help="Video source: a or b (default: a)",
    )
    parser.add_argument(
        "--audio", choices=["a", "b"], default=DEFAULTS["audio"],
        help="Audio source: a or b (default: a)",
    )
    parser.add_argument(
        "--offset", default=DEFAULTS["offset"],
        help="Audio offset relative to video, e.g. -200ms, +1.5s (default: 0ms)",
    )
    parser.add_argument(
        "--output-dir", default=DEFAULTS["output_dir"],
        help="Directory for HLS output files (default: /tmp/streammerge)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULTS["port"],
        help="HTTP server port, 0 to disable (default: 38080)",
    )
    parser.add_argument(
        "--low-latency", type=str, default=DEFAULTS["low_latency"],
        choices=["true", "false"],
        help="Enable LL-HLS mode (default: true)",
    )
    parser.add_argument(
        "--proxy-a", default="",
        help="HTTP proxy for stream A (e.g. http://host:port), empty for direct",
    )
    parser.add_argument(
        "--proxy-b", default="",
        help="HTTP proxy for stream B (e.g. http://host:port), empty for direct",
    )
    parser.add_argument(
        "--reencode", action="store_true",
        help="Force re-encode even when offset=0 (default: stream copy when possible)",
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> list[str]:
    """Validate parsed arguments. Returns list of error messages (empty = valid)."""
    errors = []

    if not OFFSET_PATTERN.match(args.offset):
        errors.append(
            f"Invalid offset format: '{args.offset}'. "
            "Expected format: [+-]<n>ms or [+-]<n>s (e.g. 500ms, -200ms, +1.5s)"
        )

    if not args.stream_a:
        errors.append("--stream-a is required")
    elif not args.stream_a.startswith(("http://", "https://")):
        errors.append(f"stream-a must be an HTTP(S) URL, got: {args.stream_a}")
    if not args.stream_b:
        errors.append("--stream-b is required")
    elif not args.stream_b.startswith(("http://", "https://")):
        errors.append(f"stream-b must be an HTTP(S) URL, got: {args.stream_b}")

    if args.video == args.audio:
        logger.info(
            "Video and audio from same source (%s) — no merge needed, "
            "but will still produce HLS output with both tracks from that source.",
            args.video
        )

    return errors


def _ensure_cooked_terminal():
    """Re-enable terminal cooked-mode flags unconditionally.

    tty.setraw() disables: ICANON (line buffering), ECHO, ISIG (Ctrl+C→SIGINT),
    ICRNL (CR→NL mapping for Enter), OPOST (output handling).
    If the previous run left the terminal raw, Python's input() reads raw bytes
    — Enter sends \\r (no newline) and Ctrl+C sends \\x03 instead of SIGINT.

    We always force-enable these flags regardless of current state. This is
    idempotent (enabling already-enabled flags is harmless) and doesn't depend
    on a saved snapshot (which would capture raw mode on the next run).
    """
    try:
        import termios
        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        # iflag[0]: ICRNL — translate CR to NL so Enter works
        # oflag[1]: OPOST — output processing (\\n → \\r\\n)
        # lflag[3]: ICANON (line mode), ECHO, ISIG (Ctrl+C → SIGINT)
        attrs[0] |= termios.ICRNL
        attrs[1] |= termios.OPOST
        attrs[3] |= termios.ICANON | termios.ECHO | termios.ISIG
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    except (termios.error, OSError, ImportError):
        pass


def _prompt(prompt_text: str, default: str = "", validator=None) -> str:
    """Prompt the user for input with a default value.

    Args:
        prompt_text: The question to display.
        default: Default value if user presses Enter.
        validator: Optional callable(str) -> str | None. Returns error message
                   if invalid, or None if valid.

    Returns:
        The user's input or the default.
    """
    _ensure_cooked_terminal()

    if default:
        display = f"{prompt_text} [{default}]: "
    else:
        display = f"{prompt_text}: "

    while True:
        try:
            value = input(display).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not value:
            value = default

        if validator:
            err = validator(value)
            if err:
                print(f"  ✗ {err}", file=sys.stderr)
                continue

        return value


def _validate_url(value: str) -> str | None:
    """Validator: must be an HTTP(S) URL."""
    if not value:
        return "URL is required"
    if not value.startswith(("http://", "https://")):
        return f"Must be an HTTP(S) URL, got: {value}"
    return None


def _validate_offset(value: str) -> str | None:
    """Validator: must match offset format."""
    if not OFFSET_PATTERN.match(value):
        return f"Invalid format: '{value}'. Expected e.g. 500ms, -200ms, +1.5s"
    return None


def _validate_port(value: str) -> str | None:
    """Validator: must be an integer 0-65535."""
    if not value:
        return None  # empty → use default
    try:
        port = int(value)
        if port < 0 or port > 65535:
            return f"Port must be 0-65535, got: {port}"
    except ValueError:
        return f"Must be a number, got: {value}"
    return None


def _validate_choice(choices: list[str]) -> callable:
    """Factory: return a validator for a fixed set of choices."""
    def validator(value: str) -> str | None:
        if value not in choices:
            return f"Must be one of: {', '.join(choices)}"
        return None
    return validator


def interactive_prompt(args: argparse.Namespace) -> argparse.Namespace:
    """Prompt the user interactively for each parameter.

    Pre-fills with values already set from CLI args (if any). Returns the
    updated namespace.
    """
    print()
    print("╔══════════════════════════════════════╗")
    print("║   Stream Merge — Interactive Setup   ║")
    print("╚══════════════════════════════════════╝")
    print("(Press Enter to accept the default, Ctrl+C to quit)")
    print()

    # ── required: stream-a ────────────────────────────────────
    default_a = args.stream_a or ""
    args.stream_a = _prompt(
        "Stream A URL (HLS .m3u8)",
        default=default_a,
        validator=_validate_url,
    )

    # ── required: stream-b ────────────────────────────────────
    default_b = args.stream_b or ""
    args.stream_b = _prompt(
        "Stream B URL (HLS .m3u8)",
        default=default_b,
        validator=_validate_url,
    )

    # ── optional: proxy A ──────────────────────────────────────
    args.proxy_a = _prompt(
        "HTTP proxy for Stream A (empty = direct, e.g. http://proxy:8080)",
        default=args.proxy_a or "",
    )
    # ── optional: proxy B ──────────────────────────────────────
    args.proxy_b = _prompt(
        "HTTP proxy for Stream B (empty = direct, e.g. http://proxy:8080)",
        default=args.proxy_b or "",
    )

    # ── optional: video source ────────────────────────────────
    args.video = _prompt(
        "Video source",
        default=args.video,
        validator=_validate_choice(["a", "b"]),
    )
    # ── optional: audio source ────────────────────────────────
    args.audio = _prompt(
        "Audio source",
        default=args.audio,
        validator=_validate_choice(["a", "b"]),
    )

    # ── optional: offset ──────────────────────────────────────
    args.offset = _prompt(
        "Audio offset (e.g. 500ms, -200ms, +1.5s)",
        default=args.offset,
        validator=_validate_offset,
    )

    # ── optional: output dir ──────────────────────────────────
    args.output_dir = _prompt(
        "Output directory",
        default=args.output_dir,
    )
    # ── optional: port ────────────────────────────────────────
    args.port = int(_prompt(
        "HTTP server port (0 = disabled)",
        default=str(args.port),
        validator=_validate_port,
    ))
    # ── optional: low-latency ─────────────────────────────────
    args.low_latency = _prompt(
        "Low-latency HLS mode",
        default=args.low_latency,
        validator=_validate_choice(["true", "false"]),
    )
    # ── optional: force reencode ───────────────────────────────
    reencode_default = "true" if args.reencode else "false"
    args.reencode = _prompt(
        "Force re-encode (no = stream copy when offset=0, faster)",
        default=reencode_default,
        validator=_validate_choice(["true", "false"]),
    ) == "true"

    print()
    print("─" * 40)
    print("Configuration complete. Starting...")
    print()
    return args


def main() -> int:
    """Entry point. Returns exit code (0 = success)."""
    import logging
    import signal
    import sys
    import threading

    from stream_merge.offset import parse_offset
    from stream_merge.stream_manager import StreamManager
    from stream_merge.controller import InteractiveController
    from stream_merge.server import HLSServer
    from stream_merge.monitor import StatusMonitor

    # ── logging setup (writes to file, not stdout) ──────────
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.FileHandler("streammerge.log", encoding="utf-8"),
        ],
    )

    # ── parse & validate ────────────────────────────────────
    args = parse_args()

    # Interactive mode: prompt for missing parameters
    if args.interactive:
        args = interactive_prompt(args)

    # After interactive mode (or direct CLI), verify required fields
    if not args.stream_a or not args.stream_b:
        print(
            "Error: --stream-a and --stream-b are required. "
            "Use --interactive for guided setup.",
            file=sys.stderr,
        )
        return 1

    errors = validate_args(args)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    offset_ms = parse_offset(args.offset)

    # ── start components ────────────────────────────────────
    manager = StreamManager(
        stream_a=args.stream_a,
        stream_b=args.stream_b,
        video=args.video,
        audio=args.audio,
        offset_ms=offset_ms,
        output_dir=args.output_dir,
        low_latency=args.low_latency == "true",
        proxy_a=args.proxy_a or "",
        proxy_b=args.proxy_b or "",
        reencode=args.reencode,
    )

    server = HLSServer(output_dir=args.output_dir, port=args.port)

    monitor = StatusMonitor(manager=manager, output_dir=args.output_dir)

    controller = InteractiveController(manager=manager)

    # ── signal handling for graceful shutdown ───────────────
    shutdown_event = threading.Event()

    def _handle_signal(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        print(f"\nReceived signal {signum}, shutting down...")
        shutdown_event.set()
        controller.shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── launch ──────────────────────────────────────────────
    print("=" * 50)
    print("Stream Merge starting")
    print(f"  Stream A: {args.stream_a}")
    print(f"  Stream B: {args.stream_b}")
    print(f"  Video: {args.video}, Audio: {args.audio}")
    print(f"  Offset: {args.offset} ({offset_ms}ms)")
    print(f"  Output: {args.output_dir}")
    print(f"  Proxy A: {args.proxy_a or 'direct'}")
    print(f"  Proxy B: {args.proxy_b or 'direct'}")
    mode = "REENCODE" if args.reencode else "STREAM COPY"
    print(f"  Mode: {mode}")
    print(f"  LL-HLS: {args.low_latency}")
    print(f"  HTTP port: {args.port if args.port else 'disabled'}")
    print("  Log file: streammerge.log")
    print("=" * 50)

    # Ensure clean shutdown on any unhandled exception in the main thread
    try:
        server.start()
        manager.start()
        monitor.start()

        # ── success confirmation ───────────────────────────────
        output_path = os.path.join(args.output_dir, "index.m3u8")
        print(f"✓ Stream merge active → {output_path}")
        if args.port:
            print(f"✓ HTTP server → http://localhost:{args.port}/index.m3u8")
        print()

        controller.run()
    except Exception:
        logger.exception("Fatal error in main loop")
        print("Fatal error — see streammerge.log for details", file=sys.stderr)
    finally:
        print("Shutting down...")
        monitor.stop()
        controller.shutdown()
        manager.stop()
        server.stop()
        print("Stream Merge exited.")

    return 0
