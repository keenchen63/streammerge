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
        # Reinit filter for codec changes (input option, goes before -i)
        "-reinit_filter", "1",
        # Stream A (input 0)
        "-i", stream_a,
    ]

    # Insert itsoffset before the second input if offset is negative
    # (we delay the video by abs(offset) to effectively advance audio)
    if offset_ms < 0:
        itsoffset_sec = abs(offset_ms) / 1000.0
        cmd.extend(["-itsoffset", str(itsoffset_sec)])

    # Stream B (input 1)
    cmd.extend(["-i", stream_b])

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

    cmd.append(output_path)

    return cmd
