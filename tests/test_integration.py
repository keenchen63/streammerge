"""Integration smoke tests for stream_merge."""

from stream_merge.cli import parse_args, validate_args
from stream_merge.command import build_ffmpeg_command
from stream_merge.offset import parse_offset


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
            "--offset=+1.5s",
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
