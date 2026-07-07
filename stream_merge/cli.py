"""CLI argument parsing and entry point for stream_merge."""

import argparse
import re
import sys
import logging

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
    args = parse_args()

    errors = validate_args(args)
    if errors:
        for err in errors:
            logger.error(err)
        return 1

    # Deferred import to avoid circular imports; the actual run logic
    # is wired in a later task.
    logger.info("Stream Merge starting with: video=%s, audio=%s, offset=%s",
                args.video, args.audio, args.offset)
    logger.info("Stream A: %s", args.stream_a)
    logger.info("Stream B: %s", args.stream_b)
    logger.info("Output: %s", args.output_dir)

    return 0
