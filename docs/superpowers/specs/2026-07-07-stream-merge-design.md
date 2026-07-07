# Stream Merge — Design Spec

**Date**: 2026-07-07  
**Status**: Approved

---

## Overview

A CLI tool that merges video and audio tracks from two independent HLS live streams into a single HLS output. The user selects which stream provides the video track, which provides the audio track, adjusts audio/video sync offset, and receives a combined low-latency HLS stream served locally.

## Requirements

### Functional

1. Accept two HLS (`.m3u8`) input stream URLs via CLI
2. Select video source: stream A or stream B
3. Select audio source: stream A or stream B
4. Apply configurable audio-to-video time offset (positive or negative)
5. Output a single combined HLS stream (`.m3u8` + TS segments) to a local directory
6. Optionally serve the output directory over HTTP for LAN consumption
7. Runtime interactive controls: adjust offset on-the-fly, switch track sources, display status

### Non-Functional

- Low-latency HLS output (< 3 seconds end-to-end)
- Stable 24/7 operation with automatic recovery from failures
- Python 3.10+ with ffmpeg as the media engine
- Clean CLI experience with structured logging

## Technical Approach

**Python + ffmpeg**: Python handles CLI, process lifecycle, interactive controls; ffmpeg handles all media processing (demux, track selection, time offset, HLS muxing).

## CLI Interface

```bash
streammerge \
  --stream-a "https://example.com/live-a/index.m3u8" \
  --stream-b "https://example.com/live-b/index.m3u8" \
  --video a \
  --audio b \
  --offset 500ms \
  --output-dir ./output \
  --port 8080
```

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--stream-a` | First HLS input stream URL | Required |
| `--stream-b` | Second HLS input stream URL | Required |
| `--video` | Video source: `a` or `b` | `a` |
| `--audio` | Audio source: `a` or `b` | `a` |
| `--offset` | Audio offset relative to video. Format: `±<n>ms` or `±<n>s` (e.g. `-200ms`, `+1.5s`) | `0ms` |
| `--output-dir` | Directory for HLS output files | `./output` |
| `--port` | HTTP server port for serving output. `0` disables the server. | `0` |
| `--low-latency` | Enable LL-HLS mode | `true` |

### Runtime Hotkeys

| Key | Action |
|-----|--------|
| `←` / `→` | Adjust audio offset by ∓50ms |
| `Shift+←` / `Shift+→` | Adjust audio offset by ∓500ms |
| `v` | Toggle video source (a ↔ b) |
| `a` | Toggle audio source (a ↔ b) |
| `s` | Print current status (offset, stream health, uptime) |
| `q` | Graceful shutdown |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      CLI (argparse)                   │
│                Parse args, start main loop            │
└──────────┬──────────────────────────┬────────────────┘
           │                          │
     ┌─────▼──────┐           ┌──────▼──────┐
     │ StreamMgr   │           │ Interactive │
     │ ffmpeg 子进程│◄─────────│ Controller  │
     │ 生命周期管理  │  调整偏移  │ 键盘热键监听 │
     └─────┬──────┘           └─────────────┘
           │
     ┌─────▼──────┐
     │  HLS Output  │
     │  .m3u8 + TS  │◄── HTTP Server (optional)
     │  file output  │     LAN stream pull
     └──────────────┘
```

### Components

| Component | Responsibility |
|-----------|---------------|
| **CLI** (`cli.py`) | Parse arguments, validate inputs, orchestrate startup |
| **StreamManager** (`stream_manager.py`) | Build ffmpeg command, spawn/monitor/restart subprocess, apply offset parameters |
| **InteractiveController** (`controller.py`) | Capture keyboard input, translate to actions, notify StreamManager |
| **HLSServer** (`server.py`) | Lightweight HTTP static file server for the output directory |
| **StatusMonitor** (`monitor.py`) | Health sampling (bitrate, segment rate), log status summaries |

### Data Flow

```
Stream A (.m3u8) ─┐
                   ├─► ffmpeg ─► output-dir/ (index.m3u8 + TS segments)
Stream B (.m3u8) ─┘    ▲
                        │
               --offset +500ms (adelay / itsoffset)
```

## ffmpeg Pipeline

### Track Selection & Merge

```
-f hls read → demux A {v:0, a:0}, B {v:0, a:0}
→ -map X:v:0 -map Y:a:0
→ audio offset filter (adelay for positive, itsoffset for negative)
→ libx264 video encode + aac audio encode
→ HLS mux output
```

### LL-HLS Output Parameters

```
-f hls
-hls_time 1
-hls_list_size 5
-hls_flags delete_segments+program_date_time+independent_segments
```

### Runtime Offset Adjustment

1. User presses hotkey → InteractiveController captures
2. New accumulated offset calculated
3. StreamManager kills current ffmpeg process gracefully
4. New ffmpeg command built with updated offset
5. ffmpeg restarts immediately (~1-2s downtime)
6. HLS player continues from new segments transparently (buffered by `hls_list_size 5`)

## Fault Tolerance

| Failure Scenario | Strategy |
|-----------------|----------|
| Input stream interruption | ffmpeg reconnect flags (`-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5`). Alert if down > 30s. |
| ffmpeg process crash | Detect exit code, auto-restart after 2s delay. Max 5 consecutive retries, then exit with error. |
| Output disk full | Detect write failure, clean old TS segments, retry. Graceful exit if still failing. |
| Input codec change | ffmpeg `-reinit_filter 1` adaptive handling. Restart on repeated failure. |

## Segment Cleanup

| Mechanism | Trigger | Behavior |
|-----------|---------|----------|
| ffmpeg `delete_segments` | Every new TS segment written | Removes segments dropped from the playlist |
| Startup cleanup | Before ffmpeg launch | Remove all stale `.ts` and `.m3u8` files from output directory |
| Periodic sweep | Every 60 seconds | If `.ts` file count exceeds `hls_list_size * 2`, log warning + delete oldest excess files by modification time (safety net for ffmpeg cleanup failure) |

## Health Monitoring

- **Per-second**: ffmpeg running status, output bitrate, segment write rate
- **Per-30-seconds**: Condensed status log line
- **Anomaly detection**: 15+ seconds without new segments → auto-restart

## Logging

- Structured stdout logs with timestamps and levels
- ffmpeg stderr redirected to `{output-dir}/ffmpeg.log`

## Project Structure

```
streammerge/
├── cli.py                  # Entry point, argument parsing
├── stream_manager.py       # ffmpeg process lifecycle
├── controller.py           # Interactive keyboard input
├── monitor.py              # Health monitoring
├── server.py               # HTTP static server
├── __init__.py
└── __main__.py             # python -m streammerge support
```

## Dependencies

- **Python 3.10+** (already available)
- **ffmpeg** (already available via homebrew)
- No additional Python packages beyond stdlib (argparse, subprocess, http.server, logging, threading, os, pathlib, time)

## Testing Strategy

- Unit tests for argument parsing, offset parsing, command building
- Integration tests with local test HLS streams (generated via ffmpeg or static files)
- Manual testing with real live streams for latency and stability validation

## Open Questions / Future Considerations

- Future: SRT/RTMP input support
- Future: Picture-in-picture / split-screen video mixing
- Future: Audio mixing (both streams audible simultaneously)
