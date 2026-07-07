"""CLI argument parsing and entry point for stream_merge."""

import argparse
import logging
import re

logger = logging.getLogger(__name__)

OFFSET_PATTERN = re.compile(r'^[+-]?\d+(\.\d+)?(ms|s)$')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and return a namespace."""
    parser = argparse.ArgumentParser(
        prog="streammerge",
        description="Merge video and audio tracks from two HLS live streams.",
    )
    parser.add_argument(
        "--stream-a", required=True,
        help="First HLS input stream URL (.m3u8)",
    )
    parser.add_argument(
        "--stream-b", required=True,
        help="Second HLS input stream URL (.m3u8)",
    )
    parser.add_argument(
        "--video", choices=["a", "b"], default="a",
        help="Video source: a or b (default: a)",
    )
    parser.add_argument(
        "--audio", choices=["a", "b"], default="a",
        help="Audio source: a or b (default: a)",
    )
    parser.add_argument(
        "--offset", default="0ms",
        help="Audio offset relative to video, e.g. -200ms, +1.5s (default: 0ms)",
    )
    parser.add_argument(
        "--output-dir", default="./output",
        help="Directory for HLS output files (default: ./output)",
    )
    parser.add_argument(
        "--port", type=int, default=0,
        help="HTTP server port, 0 to disable (default: 0)",
    )
    parser.add_argument(
        "--low-latency", type=str, default="true",
        choices=["true", "false"],
        help="Enable LL-HLS mode (default: true)",
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

    if not args.stream_a.startswith(("http://", "https://")):
        errors.append(f"stream-a must be an HTTP(S) URL, got: {args.stream_a}")
    if not args.stream_b.startswith(("http://", "https://")):
        errors.append(f"stream-b must be an HTTP(S) URL, got: {args.stream_b}")

    if args.video == args.audio:
        logger.info(
            "Video and audio from same source (%s) — no merge needed, "
            "but will still produce HLS output with both tracks from that source.",
            args.video
        )

    return errors


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

    # ── logging setup ───────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # ── parse & validate ────────────────────────────────────
    args = parse_args()

    errors = validate_args(args)
    if errors:
        for err in errors:
            logging.error(err)
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
    )

    server = HLSServer(output_dir=args.output_dir, port=args.port)

    monitor = StatusMonitor(manager=manager, output_dir=args.output_dir)

    controller = InteractiveController(manager=manager)

    # ── signal handling for graceful shutdown ───────────────
    shutdown_event = threading.Event()

    def _handle_signal(signum, frame):
        logging.info("Received signal %s, shutting down...", signum)
        shutdown_event.set()
        controller.shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── launch ──────────────────────────────────────────────
    logging.info("=" * 50)
    logging.info("Stream Merge starting")
    logging.info("  Stream A: %s", args.stream_a)
    logging.info("  Stream B: %s", args.stream_b)
    logging.info("  Video: %s, Audio: %s", args.video, args.audio)
    logging.info("  Offset: %s (%dms)", args.offset, offset_ms)
    logging.info("  Output: %s", args.output_dir)
    logging.info("  LL-HLS: %s", args.low_latency)
    logging.info("  HTTP port: %s", args.port if args.port else "disabled")
    logging.info("=" * 50)

    # Ensure clean shutdown on any unhandled exception in the main thread
    try:
        server.start()
        manager.start()
        monitor.start()
        controller.run()
    except Exception:
        logging.exception("Fatal error in main loop")
    finally:
        logging.info("Shutting down components...")
        monitor.stop()
        controller.shutdown()
        manager.stop()
        server.stop()
        logging.info("Stream Merge exited.")

    return 0
