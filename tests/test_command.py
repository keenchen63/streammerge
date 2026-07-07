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

    def test_positive_offset_uses_itsoffset_on_audio(self):
        cmd = build_ffmpeg_command(
            stream_a="https://a.example.com/live.m3u8",
            stream_b="https://b.example.com/live.m3u8",
            video="a",
            audio="b",
            offset_ms=500,
            output_dir="./output",
            low_latency=True,
        )
        # offset > 0 → delay audio → -itsoffset before audio input (B = input 1)
        # -itsoffset should be before the second -i
        assert "-itsoffset" in cmd
        # No adelay filter (we use itsoffset instead, allows stream copy)
        assert not any("adelay" in arg for arg in cmd)

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
        # Check HLS flags include expected options
        flags_idx = None
        for i, arg in enumerate(cmd):
            if arg == "-hls_flags" and i + 1 < len(cmd):
                flags_idx = i + 1
                break
        assert flags_idx is not None
        assert "append_list" in cmd[flags_idx]
        assert "independent_segments" in cmd[flags_idx]
        assert "omit_endlist" in cmd[flags_idx]

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
