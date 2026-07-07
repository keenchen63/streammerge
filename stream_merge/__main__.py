"""Allow running stream_merge via python -m stream_merge."""

from stream_merge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
