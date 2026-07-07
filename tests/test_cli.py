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
        assert args.port == 38080
        assert args.low_latency == "true"

    def test_all_args_specified(self):
        args = parse_args([
            "--stream-a", "https://a.example.com/live.m3u8",
            "--stream-b", "https://b.example.com/live.m3u8",
            "--video", "b",
            "--audio", "a",
            "--offset=-200ms",
            "--output-dir", "/tmp/merged",
            "--port", "8080",
            "--low-latency", "false",
        ])
        assert args.video == "b"
        assert args.audio == "a"
        assert args.offset == "-200ms"
        assert args.output_dir == "/tmp/merged"
        assert args.port == 8080
        assert args.low_latency == "false"

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

    def test_interactive_flag(self):
        args = parse_args(["--interactive"])
        assert args.interactive is True
        assert args.stream_a is None
        assert args.stream_b is None

    def test_missing_stream_a_caught_by_validate(self):
        args = argparse.Namespace(
            stream_a=None,
            stream_b="https://b.example.com/live.m3u8",
            video="a", audio="a", offset="0ms",
            output_dir="./output", port=0, low_latency="true",
        )
        errors = validate_args(args)
        assert any("stream-a" in e for e in errors)

    def test_missing_stream_b_caught_by_validate(self):
        args = argparse.Namespace(
            stream_a="https://a.example.com/live.m3u8",
            stream_b=None,
            video="a", audio="a", offset="0ms",
            output_dir="./output", port=0, low_latency="true",
        )
        errors = validate_args(args)
        assert any("stream-b" in e for e in errors)


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
