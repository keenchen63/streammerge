"""Build ffmpeg command for stream merging."""
from __future__ import annotations

import os


def build_ffmpeg_command(
    stream_a: str,
    stream_b: str,
    video: str,
    audio: str,
    offset_ms: int,
    output_dir: str,
    low_latency: bool,
    proxy_a: str = "",
    proxy_b: str = "",
    reencode: bool = False,
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
        proxy_a: HTTP proxy for stream A, empty for none.
        proxy_b: HTTP proxy for stream B, empty for none.
        reencode: If True, force re-encode even when offset=0.

    Returns:
        List of command arguments suitable for subprocess.Popen.
    """
    video_input = 0 if video == "a" else 1
    audio_input = 0 if audio == "a" else 1

    # Stream copy when possible (offset=0, no reencode forced).
    # This avoids CPU-heavy re-encoding — ffmpeg just remuxes the tracks.
    use_copy = (offset_ms == 0 and not reencode)

    output_path = os.path.join(output_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        # Reconnect settings for input resilience
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        # Reinit filter for codec changes (input option, goes before -i)
        "-reinit_filter", "1",
    ]

    # Stream A — with optional per-input proxy and buffer queue
    if proxy_a:
        cmd.extend(["-http_proxy", proxy_a])
    cmd.extend(["-thread_queue_size", "1024"])
    cmd.extend(["-i", stream_a])

    # Insert itsoffset before the second input if offset is negative
    if offset_ms < 0:
        itsoffset_sec = abs(offset_ms) / 1000.0
        cmd.extend(["-itsoffset", str(itsoffset_sec)])

    # Stream B — with optional per-input proxy and buffer queue
    if proxy_b:
        cmd.extend(["-http_proxy", proxy_b])
    cmd.extend(["-thread_queue_size", "1024"])
    cmd.extend(["-i", stream_b])

    # Map video track
    cmd.extend(["-map", f"{video_input}:v:0"])
    # Map audio track
    cmd.extend(["-map", f"{audio_input}:a:0"])

    # ── encoding strategy ─────────────────────────────────────
    if use_copy:
        # Stream copy: no re-encoding, near-zero CPU.
        # Works when both sources are H.264+AAC (the typical case).
        cmd.extend(["-c:v", "copy"])
        cmd.extend(["-c:a", "copy"])
    else:
        # Need filters (offset != 0 or forced reencode) — must re-encode.
        # Audio delay filter for positive offset
        if offset_ms > 0:
            cmd.extend(["-af", f"adelay={offset_ms}|{offset_ms}"])

        # Video: ultrafast preset + zerolatency tuning for live streaming
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "23",
        ])
        # Audio: aac at standard bitrate
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # ── HLS output settings ───────────────────────────────────
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

    cmd.append(output_path)

    return cmd
