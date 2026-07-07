# Stream Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that merges video+audio tracks from two HLS streams into a single LL-HLS output with runtime offset adjustment.

**Architecture:** Python + ffmpeg. Python handles CLI, process lifecycle, interactive keyboard controls, health monitoring, and optional HTTP serving. ffmpeg handles all media processing (demux, track selection, time offset via adelay/itsoffset, HLS muxing). Pure stdlib — no packages beyond Python 3.10+ and ffmpeg.

**Tech Stack:** Python 3.10+, ffmpeg, stdlib only (argparse, subprocess, http.server, logging, threading, os, pathlib, time, termios, tty, select).

## Global Constraints

- Python 3.10+ (already available)
- ffmpeg must be on PATH (already installed via homebrew)
- Zero third-party Python packages — stdlib only
- Test-driven: write failing test first, run it to see it fail, implement, run to see it pass, commit
- Output directory defaults to `./output` relative to CWD

---

### Task 1: Project Scaffolding

**Files:**
- Create: `stream_merge/__init__.py`
- Create: `stream_merge/__main__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: package structure so `python -m stream_merge` works, `tests/` directory for all subsequent tasks

- [ ] **Step 1: Create stream_merge package directory**

```bash
mkdir -p stream_merge tests
```

- [ ] **Step 2: Write __init__.py**

Create `stream_merge/__init__.py`:
```python
"""Stream Merge — merge video and audio tracks from two HLS live streams."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write tests/__init__.py**

Create `tests/__init__.py`:
```python
# Test suite for stream_merge
```

- [ ] **Step 4: Write __main__.py**

Create `stream_merge/__main__.py`:
```python
"""Allow running stream_merge via python -m stream_merge."""

from stream_merge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Commit**

```bash
git add stream_merge/__init__.py stream_merge/__main__.py tests/__init__.py
git commit -m "feat: scaffold stream_merge package structure"

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 2: CLI Argument Parsing

**Files:**
- Create: `stream_merge/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing (first functional module)
- Produces:
  - `parse_args(argv: list[str] | None = None) -> argparse.Namespace` — parse CLI arguments, returns namespace with fields: `stream_a`, `stream_b`, `video`, `audio`, `offset`, `output_dir`, `port`, `low_latency`
  - `validate_args(args: argparse.Namespace) -> list[str]` — returns list of error messages (empty = valid)
  - `main() -> int` — entry point, calls parse_args + validate_args, returns exit code

- [ ] **Step 1: Write failing test for argument parsing**

Create `tests/test_cli.py`:
```python
"""Tests for CLI argument parsing."""

import argparse
import pytest
from stream_merge.cli import parse_args, validate_args


class TestParseArgs:
    """Tests for parse_args()."""

    def test_minimal_required_args(self):
        args = parse_args([
            "--stream-a", "https://example.com/live/a.m3u8",
            "--stream-b", "https://example.com/live/b.m3u8",
        ])
        assert args.stream_a == "https://example.com/live/a.m3u8"
        assert args.stream_b == "https://example.com/live/b.m3u8"
        assert args.video == "a"
        assert args.audio == "a"
        assert args.offset == "0ms"
        assert args.output_dir == "./output"
        assert args.port == 0
        assert args.low_latency is True

    def test_all_args_specified(self):
        args = parse_args([
            "--stream-a", "https://a.example.com/live.m3u8",
            "--stream-b", "https://b.example.com/live.m3u8",
            "--video", "b",
            "--audio", "a",
            "--offset", "-200ms",
            "--output-dir", "/tmp/merged",
            "--port", "8080",
            "--low-latency", "false",
        ])
        assert args.video == "b"
        assert args.audio == "a"
        assert args.offset == "-200ms"
        assert args.output_dir == "/tmp/merged"
        assert args.port == 8080
        assert args.low_latency is False

    def test_video_must_be_a_or_b(self):
        with pytest.raises(SystemExit):
            parse_args([
                "--stream-a", "https://a.example.com/live.m3u8",
                "--stream-b", "https://b.example.com/live.m3u8",
                "--video", "c",
            ])

    def test_audio_must_be_a_or_b(self):
        with pytest.raises(SystemExit):
            parse_args([
                "--stream-a", "https://a.example.com/live.m3u8",
                "--stream-b", "https://b.example.com/live.m3u8",
                "--audio", "c",
            ])

    def test_missing_stream_a_raises_error(self):
        with pytest.raises(SystemExit):
            parse_args(["--stream-b", "https://b.example.com/live.m3u8"])

    def test_missing_stream_b_raises_error(self):
        with pytest.raises(SystemExit):
            parse_args(["--stream-a", "https://a.example.com/live.m3u8"])


class TestValidateArgs:
    """Tests for validate_args()."""

    def test_valid_args_no_errors(self):
        args = argparse.Namespace(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset="0ms",
            output_dir="./output",
            port=0,
            low_latency=True,
        )
        errors = validate_args(args)
        assert errors == []

    def test_same_source_no_merge_needed_warns(self):
        args = argparse.Namespace(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="a",
            offset="0ms",
            output_dir="./output",
            port=0,
            low_latency=True,
        )
        errors = validate_args(args)
        assert errors == []  # valid but logged as info, not error

    def test_invalid_offset_format(self):
        args = argparse.Namespace(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset="abc",
            output_dir="./output",
            port=0,
            low_latency=True,
        )
        errors = validate_args(args)
        assert len(errors) > 0
        assert any("offset" in e.lower() for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_cli.py -v
```
Expected: FAIL — module `stream_merge.cli` not found or functions not defined.

- [ ] **Step 3: Write cli.py implementation**

Create `stream_merge/cli.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_cli.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stream_merge/cli.py tests/test_cli.py
git commit -m "feat: add CLI argument parsing with validation

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 3: Offset Parser Utility

**Files:**
- Create: `stream_merge/offset.py`
- Create: `tests/test_offset.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `parse_offset(offset_str: str) -> int` — parse "500ms", "-200ms", "+1.5s" into integer milliseconds
  - `format_offset(ms: int) -> str` — format integer ms back to human-readable string (e.g., 1500 → "+1.5s")

- [ ] **Step 1: Write failing test for offset parsing**

Create `tests/test_offset.py`:
```python
"""Tests for offset parsing utilities."""

import pytest
from stream_merge.offset import parse_offset, format_offset


class TestParseOffset:
    """Tests for parse_offset()."""

    def test_zero(self):
        assert parse_offset("0ms") == 0

    def test_positive_ms(self):
        assert parse_offset("500ms") == 500

    def test_negative_ms(self):
        assert parse_offset("-200ms") == -200

    def test_explicit_positive_ms(self):
        assert parse_offset("+300ms") == 300

    def test_positive_seconds(self):
        assert parse_offset("1.5s") == 1500

    def test_negative_seconds(self):
        assert parse_offset("-0.5s") == -500

    def test_explicit_positive_seconds(self):
        assert parse_offset("+2s") == 2000

    def test_integer_seconds(self):
        assert parse_offset("3s") == 3000

    def test_decimal_ms(self):
        assert parse_offset("1.5ms") == 1  # rounds toward zero via int()

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid offset format"):
            parse_offset("abc")

    def test_no_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid offset format"):
            parse_offset("500")

    def test_wrong_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid offset format"):
            parse_offset("500m")


class TestFormatOffset:
    """Tests for format_offset()."""

    def test_zero(self):
        assert format_offset(0) == "0ms"

    def test_positive_ms_under_second(self):
        assert format_offset(500) == "500ms"

    def test_negative_ms_under_second(self):
        assert format_offset(-300) == "-300ms"

    def test_positive_exact_seconds(self):
        assert format_offset(2000) == "+2.0s"

    def test_negative_exact_seconds(self):
        assert format_offset(-1500) == "-1.5s"

    def test_fractional_seconds(self):
        assert format_offset(1500) == "+1.5s"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_offset.py -v
```
Expected: FAIL — module `stream_merge.offset` not found.

- [ ] **Step 3: Write offset.py implementation**

Create `stream_merge/offset.py`:
```python
"""Offset parsing and formatting utilities.

Offsets represent time in milliseconds (int), with string representations
like "500ms", "-200ms", "+1.5s".
"""

import re

_OFFSET_RE = re.compile(r'^([+-]?\d+(?:\.\d+)?)(ms|s)$')


def parse_offset(offset_str: str) -> int:
    """Parse an offset string into integer milliseconds.

    Args:
        offset_str: String like "500ms", "-200ms", "+1.5s".

    Returns:
        Offset in milliseconds (integer).

    Raises:
        ValueError: If the string format is invalid.
    """
    match = _OFFSET_RE.match(offset_str)
    if not match:
        raise ValueError(
            f"Invalid offset format: '{offset_str}'. "
            "Expected [+-]<number>ms or [+-]<number>s (e.g. 500ms, -200ms, +1.5s)"
        )
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "s":
        value *= 1000
    return int(value)


def format_offset(ms: int) -> str:
    """Format an integer millisecond offset as a human-readable string.

    Args:
        ms: Offset in milliseconds.

    Returns:
        String like "0ms", "500ms", "+1.5s", "-300ms".
    """
    if ms == 0:
        return "0ms"
    if abs(ms) < 1000 or ms % 1000 != 0:
        return f"{ms}ms"
    sign = "+" if ms > 0 else "-"
    seconds = abs(ms) / 1000.0
    if seconds == int(seconds):
        return f"{sign}{int(seconds)}.0s"
    # Format to 1 decimal place, strip trailing zeros after decimal
    formatted = f"{seconds:.1f}"
    return f"{sign}{formatted}s"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_offset.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stream_merge/offset.py tests/test_offset.py
git commit -m "feat: add offset parser and formatter utilities

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 4: ffmpeg Command Builder

**Files:**
- Create: `stream_merge/command.py`
- Create: `tests/test_command.py`

**Interfaces:**
- Consumes:
  - `parse_offset(offset_str: str) -> int` from `stream_merge.offset`
- Produces:
  - `build_ffmpeg_command(stream_a: str, stream_b: str, video: str, audio: str, offset_ms: int, output_dir: str, low_latency: bool) -> list[str]` — returns full ffmpeg command as a list of arguments

- [ ] **Step 1: Write failing test for command builder**

Create `tests/test_command.py`:
```python
"""Tests for ffmpeg command building."""

from stream_merge.command import build_ffmpeg_command


class TestBuildFfmpegCommand:
    """Tests for build_ffmpeg_command()."""

    def test_basic_command_structure(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=0,
            output_dir="./output",
            low_latency=True,
        )
        # First arg is ffmpeg
        assert cmd[0] == "ffmpeg"
        # Should contain input flags for stream A
        assert "-i" in cmd
        assert "https://a.example.com/live.m3u8" in cmd
        assert "https://b.example.com/live.m3u8" in cmd
        # Output at the end
        assert cmd[-1].endswith("index.m3u8")

    def test_video_from_a_audio_from_b_maps(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=0,
            output_dir="./output",
            low_latency=True,
        )
        # video from input 0, audio from input 1
        assert "-map" in cmd
        maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
        assert "0:v:0" in maps
        assert "1:a:0" in maps

    def test_video_and_audio_from_same_source(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="b",
            audio="b",
            offset_ms=0,
            output_dir="./output",
            low_latency=True,
        )
        maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
        # Both tracks from input 1 (stream B)
        assert "1:v:0" in maps
        assert "1:a:0" in maps

    def test_positive_offset_adds_adelay(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=500,
            output_dir="./output",
            low_latency=True,
        )
        # adelay filter should be present
        adelay_args = [arg for arg in cmd if "adelay" in arg]
        assert len(adelay_args) > 0
        # 500ms = "500|500" (stereo delay)
        assert "500" in adelay_args[0]

    def test_negative_offset_adds_itsoffset(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=-300,
            output_dir="./output",
            low_latency=True,
        )
        # -itsoffset should be present before the audio input
        assert "-itsoffset" in cmd

    def test_low_latency_hls_flags(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=0,
            output_dir="./output",
            low_latency=True,
        )
        # Check HLS flags include delete_segments
        flags_idx = None
        for i, arg in enumerate(cmd):
            if arg == "-hls_flags" and i + 1 < len(cmd):
                flags_idx = i + 1
                break
        assert flags_idx is not None
        assert "delete_segments" in cmd[flags_idx]
        assert "independent_segments" in cmd[flags_idx]

    def test_reconnect_flags_present(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=0,
            output_dir="./output",
            low_latency=True,
        )
        assert "-reconnect" in cmd
        assert "1" in cmd  # reconnect value
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_command.py -v
```
Expected: FAIL — module `stream_merge.command` not found.

- [ ] **Step 3: Write command.py implementation**

Create `stream_merge/command.py`:
```python
"""Build ffmpeg command for stream merging."""

import os


def build_ffmpeg_command(
    stream_a: str,
    stream_b: str,
    video: str,
    audio: str,
    offset_ms: int,
    output_dir: str,
    low_latency: bool,
) -> list[str]:
    """Build the ffmpeg command as a list of arguments.

    Args:
        stream_a: URL of first HLS stream.
        stream_b: URL of second HLS stream.
        video: "a" or "b" — which stream provides the video track.
        audio: "a" or "b" — which stream provides the audio track.
        offset_ms: Audio offset in milliseconds (positive = delay audio,
                   negative = advance audio via itsoffset on video).
        output_dir: Directory for HLS output files.
        low_latency: Whether to use LL-HLS settings.

    Returns:
        List of command arguments suitable for subprocess.Popen.
    """
    video_input = 0 if video == "a" else 1
    audio_input = 0 if audio == "a" else 1

    output_path = os.path.join(output_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        # Reconnect settings for input resilience
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        # Stream A (input 0)
        "-i", stream_a,
        # Stream B (input 1) — itsoffset handled below if needed
    ]

    # Insert itsoffset before the second input if offset is negative
    # (we delay the video by abs(offset) to effectively advance audio)
    input_b_index = len(cmd)
    if offset_ms < 0:
        itsoffset_sec = abs(offset_ms) / 1000.0
        cmd.insert(input_b_index - 2, "-itsoffset")
        cmd.insert(input_b_index - 1, str(itsoffset_sec))

    cmd.append("-i")
    cmd.append(stream_b)

    # Map video track
    cmd.extend(["-map", f"{video_input}:v:0"])
    # Map audio track
    cmd.extend(["-map", f"{audio_input}:a:0"])

    # Audio delay filter for positive offset
    if offset_ms > 0:
        # adelay takes delay per channel in ms; "500|500" for stereo
        cmd.extend(["-af", f"adelay={offset_ms}|{offset_ms}"])
    elif offset_ms < 0:
        # When using itsoffset on the video input, audio is effectively
        # delayed relative to video. We already applied itsoffset above.
        pass

    # Video codec
    cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])

    # Audio codec
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # HLS output settings
    if low_latency:
        cmd.extend([
            "-f", "hls",
            "-hls_time", "1",
            "-hls_list_size", "5",
            "-hls_flags",
            "delete_segments+program_date_time+independent_segments",
        ])
    else:
        cmd.extend([
            "-f", "hls",
            "-hls_time", "6",
            "-hls_list_size", "10",
            "-hls_flags", "delete_segments+program_date_time",
        ])

    # Reinit filter for codec changes
    cmd.append("-reinit_filter")
    cmd.append("1")

    cmd.append(output_path)

    return cmd
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_command.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stream_merge/command.py tests/test_command.py
git commit -m "feat: add ffmpeg command builder with track mapping and offset

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 5: StreamManager — ffmpeg Process Lifecycle

**Files:**
- Create: `stream_merge/stream_manager.py`

**Interfaces:**
- Consumes:
  - `build_ffmpeg_command(...)` from `stream_merge.command`
- Produces:
  - `class StreamManager` with:
    - `__init__(stream_a, stream_b, video, audio, offset_ms, output_dir, low_latency)` — store config
    - `start() -> None` — launch ffmpeg subprocess
    - `stop() -> None` — terminate ffmpeg gracefully (SIGTERM) then force (SIGKILL)
    - `restart() -> None` — stop + start with current config
    - `update_offset(ms: int) -> None` — update offset and trigger restart
    - `update_source(video: str | None, audio: str | None) -> None` — update track sources and trigger restart
    - `is_running() -> bool` — check if ffmpeg process is alive
    - `start_time -> float | None` — monotonic timestamp of when current ffmpeg started
    - `restart_count -> int` — number of restarts since creation

- [ ] **Step 1: Write StreamManager implementation**

Create `stream_merge/stream_manager.py`:
```python
"""StreamManager — manages ffmpeg subprocess lifecycle."""

import logging
import os
import signal
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
```

- [ ] **Step 2: Commit**

```bash
git add stream_merge/stream_manager.py
git commit -m "feat: add StreamManager for ffmpeg process lifecycle

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 6: HLSServer — HTTP Static File Server

**Files:**
- Create: `stream_merge/server.py`

**Interfaces:**
- Consumes: nothing (stdlib `http.server`)
- Produces:
  - `class HLSServer` with:
    - `__init__(output_dir: str, port: int)` — configure server
    - `start() -> None` — start serving in a daemon thread
    - `stop() -> None` — shutdown
    - `is_running() -> bool` — check status

- [ ] **Step 1: Write HLSServer implementation**

Create `stream_merge/server.py`:
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add stream_merge/server.py
git commit -m "feat: add HLSServer for LAN stream access

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 7: InteractiveController — Keyboard Input

**Files:**
- Create: `stream_merge/controller.py`

**Interfaces:**
- Consumes:
  - `StreamManager` from `stream_merge.stream_manager`
  - `format_offset(ms: int) -> str` from `stream_merge.offset`
- Produces:
  - `class InteractiveController` with:
    - `__init__(manager: StreamManager)` — bind to a StreamManager
    - `run() -> None` — blocking loop reading keyboard input and dispatching actions
    - `shutdown() -> None` — signal the controller to exit

- [ ] **Step 1: Write InteractiveController implementation**

Create `stream_merge/controller.py`:
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add stream_merge/controller.py
git commit -m "feat: add InteractiveController for runtime hotkey control

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 8: Monitor — Health Checks & Segment Sweep

**Files:**
- Create: `stream_merge/monitor.py`

**Interfaces:**
- Consumes:
  - `StreamManager` from `stream_merge.stream_manager`
  - `format_offset(ms: int) -> str` from `stream_merge.offset`
- Produces:
  - `class StatusMonitor` with:
    - `__init__(manager: StreamManager, output_dir: str)` — bind to manager + directory
    - `start() -> None` — start background monitoring thread
    - `stop() -> None` — stop monitoring
    - `run_once() -> None` — perform a single health check + sweep cycle

- [ ] **Step 1: Write StatusMonitor implementation**

Create `stream_merge/monitor.py`:
```python
"""StatusMonitor — health checks, logging, and segment cleanup sweep."""

import logging
import os
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
        max_files = 5 * 2  # hls_list_size * 2
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
```

- [ ] **Step 2: Commit**

```bash
git add stream_merge/monitor.py
git commit -m "feat: add StatusMonitor for health checks and segment sweeping

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 9: Wire Everything Together — Main Entry Point

**Files:**
- Modify: `stream_merge/cli.py` — replace placeholder `main()` with full orchestration

**Interfaces:**
- Consumes: all previously created modules
- Produces: working `streammerge` CLI tool

- [ ] **Step 1: Update cli.py main() with full orchestration**

Replace the `main()` function in `stream_merge/cli.py` with:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add stream_merge/cli.py
git commit -m "feat: wire all components together in main entry point

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 10: Integration Validation

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: full assembled CLI tool
- Produces: integration smoke tests

- [ ] **Step 1: Write integration smoke test**

Create `tests/test_integration.py`:
```python
"""Integration smoke tests for stream_merge."""

import os
import shutil
import tempfile
import time
from unittest import mock

from stream_merge.cli import parse_args, validate_args, main
from stream_merge.command import build_ffmpeg_command
from stream_merge.offset import parse_offset, format_offset


class TestEndToEndArgParsing:
    """Test the full argument-to-command pipeline."""

    def test_full_pipeline_with_defaults(self):
        args = parse_args([
            "--stream-a", "https://a.example.com/live.m3u8",
            "--stream-b", "https://b.example.com/live.m3u8",
        ])
        errors = validate_args(args)
        assert errors == []
        offset_ms = parse_offset(args.offset)
        assert offset_ms == 0

        cmd = build_ffmpeg_command(
            stream_a=args.stream_a,
            stream_b=args.stream_b,
            video=args.video,
            audio=args.audio,
            offset_ms=offset_ms,
            output_dir=args.output_dir,
            low_latency=(args.low_latency == "true"),
        )
        assert cmd[0] == "ffmpeg"
        assert "https://a.example.com/live.m3u8" in cmd
        assert "https://b.example.com/live.m3u8" in cmd

    def test_video_b_audio_a_with_offset(self):
        args = parse_args([
            "--stream-a", "https://a.example.com/live.m3u8",
            "--stream-b", "https://b.example.com/live.m3u8",
            "--video", "b",
            "--audio", "a",
            "--offset", "+1.5s",
        ])
        errors = validate_args(args)
        assert errors == []
        offset_ms = parse_offset(args.offset)
        assert offset_ms == 1500

        cmd = build_ffmpeg_command(
            stream_a=args.stream_a,
            stream_b=args.stream_b,
            video=args.video,
            audio=args.audio,
            offset_ms=offset_ms,
            output_dir=args.output_dir,
            low_latency=True,
        )
        maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
        assert "1:v:0" in maps  # video from stream B (input 1)
        assert "0:a:0" in maps  # audio from stream A (input 0)
        # positive offset adds adelay
        assert any("adelay" in arg for arg in cmd)
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all tests from all modules PASS.

- [ ] **Step 3: Create a convenience runner script**

Create `streammerge` (no extension, at repo root):

```bash
#!/usr/bin/env python3
"""Convenience entry point for stream_merge."""
import sys
from stream_merge.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

Make it executable:
```bash
chmod +x streammerge
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py streammerge
git commit -m "feat: add integration test and convenience runner script

Co-Authored-By: Claude <noreply@anthropic.com>
```
```

---

### Task 11: Dry-Run & Manual Validation

**Files:**
- No new files — manual validation task

- [ ] **Step 1: Verify CLI help output**

```bash
python -m stream_merge --help
```
Expected: full help text with all arguments listed.

- [ ] **Step 2: Verify validation catches bad input**

```bash
python -m stream_merge --stream-a not-a-url --stream-b also-bad --offset abc
```
Expected: error messages for invalid URL and invalid offset.

- [ ] **Step 3: Verify ffmpeg is available**

```bash
ffmpeg -version | head -1
```
Expected: ffmpeg version string.

- [ ] **Step 4: Dry-run with mock — confirm command constructed correctly**

```bash
python -c "
from stream_merge.command import build_ffmpeg_command
cmd = build_ffmpeg_command(
    'https://a.example.com/live.m3u8',
    'https://b.example.com/live.m3u8',
    video='a', audio='b', offset_ms=300,
    output_dir='/tmp/test', low_latency=True,
)
print(' '.join(cmd))
"
```
Expected: printed ffmpeg command with correct maps, adelay, HLS flags.
