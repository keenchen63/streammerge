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
    hls_lax_a: bool = False,
    hls_lax_b: bool = False,
    queue_size: int = 16384,
) -> list[str]:
    """Build the ffmpeg command as a list of arguments.

    Offset is implemented via -itsoffset (pure timestamp shift on the input).
    This does NOT require re-encoding — stream copy works regardless of offset.

    Args:
        stream_a: URL of first HLS stream.
        stream_b: URL of second HLS stream.
        video: "a" or "b" — which stream provides the video track.
        audio: "a" or "b" — which stream provides the audio track.
        offset_ms: Audio offset: +N = audio behind video (delay audio),
                   -N = audio ahead of video (delay video).
        output_dir: Directory for HLS output files.
        low_latency: Whether to use LL-HLS settings.
        proxy_a: HTTP proxy for stream A, empty for none.
        proxy_b: HTTP proxy for stream B, empty for none.
        reencode: If True, force re-encode instead of stream copy.

    Returns:
        List of command arguments suitable for subprocess.Popen.
    """
    video_input = 0 if video == "a" else 1
    audio_input = 0 if audio == "a" else 1

    use_copy = not reencode

    output_path = os.path.join(output_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        # Input buffering & resilience
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_on_http_error", "1",
        "-reconnect_delay_max", "10",
        "-reinit_filter", "1",
        # Reuse TLS sessions for HTTPS HLS (avoids re-handshake per segment)
        "-multiple_requests", "1",
        # Faster probe for HLS live streams (default: 5s → 2s)
        "-analyzeduration", "2000000",
        # Connection timeout 15s
        "-timeout", "15000000",
        "-rw_timeout", "15000000",
        # Timestamp correction for streams with broken PTS
        "-fflags", "+genpts+discardcorrupt",
    ]

    # ── itsoffset target ──────────────────────────────────────
    # -itsoffset delays timestamps of the NEXT -i by N seconds.
    # offset > 0: audio behind → delay audio timestamp (shift audio input)
    # offset < 0: audio ahead → delay video timestamp (shift video input)
    itsoffset_target = None  # "a", "b", or None
    if offset_ms > 0:
        itsoffset_target = audio       # delay the audio source
    elif offset_ms < 0:
        itsoffset_target = video       # delay the video source

    itsoffset_sec = abs(offset_ms) / 1000.0 if offset_ms != 0 else 0

    # ── input A ───────────────────────────────────────────────
    if proxy_a:
        cmd.extend(["-http_proxy", proxy_a])
    if itsoffset_target == "a":
        cmd.extend(["-itsoffset", str(itsoffset_sec)])
    if hls_lax_a:
        # Force HLS demuxer + accept non-standard segment URLs
        cmd.extend(["-f", "hls", "-extension_picky", "0"])
    if proxy_a or stream_a.startswith("https"):
        cmd.extend(["-multiple_requests", "1"])
    cmd.extend(["-thread_queue_size", str(queue_size)])
    cmd.extend(["-i", stream_a])

    # ── input B ───────────────────────────────────────────────
    if proxy_b:
        cmd.extend(["-http_proxy", proxy_b])
    if itsoffset_target == "b":
        cmd.extend(["-itsoffset", str(itsoffset_sec)])
    if hls_lax_b:
        cmd.extend(["-f", "hls", "-extension_picky", "0"])
    if proxy_b or stream_b.startswith("https"):
        cmd.extend(["-multiple_requests", "1"])
    cmd.extend(["-thread_queue_size", str(queue_size)])
    cmd.extend(["-i", stream_b])

    # ── track mapping ─────────────────────────────────────────
    cmd.extend(["-map", f"{video_input}:v:0"])
    cmd.extend(["-map", f"{audio_input}:a:0"])

    # ── encoding ──────────────────────────────────────────────
    if use_copy:
        cmd.extend(["-c:v", "copy"])
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "23",
        ])
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # ── HLS output ────────────────────────────────────────────
    # Note: we do NOT use delete_segments — segments are cleaned up by
    # the monitor's periodic sweep instead. This keeps old segments
    # available during network drops so players don't loop/stutter.
    if low_latency:
        cmd.extend([
            "-f", "hls",
            "-hls_time", "1",
            "-hls_list_size", "10",
            "-hls_flags",
            "append_list+program_date_time+independent_segments+omit_endlist",
        ])
    else:
        cmd.extend([
            "-f", "hls",
            "-hls_time", "6",
            "-hls_list_size", "10",
            "-hls_flags",
            "append_list+program_date_time+omit_endlist",
        ])

    cmd.append(output_path)

    return cmd
