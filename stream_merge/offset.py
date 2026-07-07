"""Offset parsing and formatting utilities.
from __future__ import annotations

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
    if abs(ms) < 1000:
        return f"{ms}ms"
    sign = "+" if ms > 0 else "-"
    seconds = abs(ms) / 1000.0
    if seconds == int(seconds):
        return f"{sign}{int(seconds)}.0s"
    # Format to 1 decimal place
    formatted = f"{seconds:.1f}"
    return f"{sign}{formatted}s"
