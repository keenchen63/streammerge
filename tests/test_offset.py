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
