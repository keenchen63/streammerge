# Stream Merge

合并两个 HLS 直播流的视频和音轨的 CLI 工具。选择保留哪个流的视频轨、哪个流的音频轨，调整音画同步偏移，输出合并后的 LL-HLS 流。

## 快速开始

```bash
# 交互式启动（推荐）：逐项输入参数
./streammerge --interactive

# 或直接通过命令行参数启动
./streammerge \
  --stream-a "https://live-a.example.com/index.m3u8" \
  --stream-b "https://live-b.example.com/index.m3u8" \
  --video a \
  --audio b
```

输出文件默认写到 `./output/` 目录，包含 `index.m3u8` 播放列表和 TS 分片。

### 交互式启动

使用 `-i` / `--interactive` 启动时，程序会逐项询问每个参数，显示默认值，直接按 Enter 即可接受：

```
╔══════════════════════════════════════╗
║   Stream Merge — Interactive Setup   ║
╚══════════════════════════════════════╝
(Press Enter to accept the default, Ctrl+C to quit)

Stream A URL (HLS .m3u8) []: https://live-a.example.com/index.m3u8
Stream B URL (HLS .m3u8) []: https://live-b.example.com/index.m3u8
Video source [a]:
Audio source [a]: b
Audio offset (e.g. 500ms, -200ms, +1.5s) [0ms]:
Output directory [./output]:
HTTP server port (0 = disabled) [0]:
Low-latency HLS mode [true]:
```

也支持**混合模式**：命令行参数 + `-i`，已传入的参数会作为交互提示的默认值。

## 环境要求

- **Python 3.10+**
- **ffmpeg**（PATH 中可用）

无需安装任何第三方 Python 包，仅使用标准库。

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-i` / `--interactive` | 标志 | - | 进入交互式提示模式，逐项输入参数 |
| `--stream-a` | URL | 必填* | 第一条 HLS 输入流地址（`.m3u8`） |
| `--stream-b` | URL | 必填* | 第二条 HLS 输入流地址（`.m3u8`） |
| `--video` | `a` 或 `b` | `a` | 视频轨来源 |
| `--audio` | `a` 或 `b` | `a` | 音频轨来源 |
| `--offset` | 字符串 | `0ms` | 音频相对视频的时间偏移 |
| `--output-dir` | 路径 | `./output` | HLS 输出目录 |
| `--port` | 整数 | `0` | HTTP 服务端口，`0` 表示禁用 |
| `--low-latency` | `true`/`false` | `true` | 启用低延迟 HLS 模式 |

> *`--stream-a` 和 `--stream-b` 为必填项，但可通过 `-i` 交互式输入，无需在命令行指定。

### offset 格式

```
[+/-]<数字>ms   → 毫秒
[+/-]<数字>s    → 秒
```

示例：

| 值 | 含义 |
|----|------|
| `0ms` | 无偏移 |
| `500ms` | 音频延迟 500 毫秒 |
| `-200ms` | 视频延迟 200 毫秒（等效于音频提前） |
| `+1.5s` | 音频延迟 1.5 秒 |
| `-0.5s` | 视频延迟 0.5 秒 |

> **注意**：Shell 中负值需用 `=` 连接，避免被解析为选项：`--offset=-200ms`

## 使用场景

### 场景 1：基本合流

用流 A 的视频 + 流 B 的音频，输出到指定目录：

```bash
./streammerge \
  --stream-a "https://camera.example.com/live.m3u8" \
  --stream-b "https://audio.example.com/live.m3u8" \
  --video a \
  --audio b \
  --output-dir ./merged
```

### 场景 2：音画同步修正

音频比画面慢半秒，把音频提前：

```bash
./streammerge \
  --stream-a "https://video.example.com/live.m3u8" \
  --stream-b "https://audio.example.com/live.m3u8" \
  --video a \
  --audio b \
  --offset=-500ms \
  --output-dir ./synced
```

### 场景 3：局域网拉流服务

输出合并流并启动 HTTP 服务器，局域网内其他设备可直接拉流：

```bash
./streammerge \
  --stream-a "https://source-a.example.com/live.m3u8" \
  --stream-b "https://source-b.example.com/live.m3u8" \
  --video a \
  --audio b \
  --port 8080 \
  --output-dir ./public
```

其他设备访问 `http://<你的IP>:8080/index.m3u8` 即可播放。

### 场景 4：标准延迟模式

需要更大的缓冲提高稳定性时，关闭低延迟模式：

```bash
./streammerge \
  --stream-a "https://source-a.example.com/live.m3u8" \
  --stream-b "https://source-b.example.com/live.m3u8" \
  --video a \
  --audio b \
  --low-latency false
```

## 运行时控制

程序启动后进入交互模式。**调整采用"暂存 → 提交"模式**：所有方向键和切换操作会先暂存，按 `Enter` 后一次性生效（只重启一次 ffmpeg），按 `r` 可取消暂存。

| 按键 | 功能 |
|------|------|
| `←` / `→` | 音频偏移暂存 ±50ms（微调） |
| `Shift+←` / `Shift+→` | 音频偏移暂存 ±500ms（粗调） |
| `[` / `]` | 音频偏移暂存 ±500ms（等效粗调） |
| `+` / `-` | 音频偏移暂存 ±50ms（等效微调） |
| `v` | 暂存视频源切换（a ↔ b） |
| `a` | 暂存音频源切换（a ↔ b） |
| `Enter` | **提交所有暂存调整**，一次性重启 ffmpeg |
| `r` | 取消所有暂存调整 |
| `s` | 显示当前状态（偏移值、运行时长、重启次数） |
| `h` | 显示热键帮助 |
| `q` | 退出（有待提交的调整时会提醒） |

### 交互示例

```
$ ./streammerge --stream-a ... --stream-b ... --video a --audio b

Stream Merge starting
  Video: a, Audio: b
  ...
Interactive mode active. Press 'h' for help, 'q' to quit.

[按 → 键]
[PENDING] offset → +50ms (Δ +50ms)  |  Enter=commit  r=cancel

[按 → 键]
[PENDING] offset → +100ms (Δ +100ms)  |  Enter=commit  r=cancel

[按 Enter]
>>> COMMITTED: offset 0ms → +100ms

[按 s]
STATUS | offset=+100ms | video=a | audio=b | ffmpeg=running | uptime=45s | restarts=1
```

## 日志

- **stdout**：仅显示用户层面的信息（启动配置、状态、调整预览）
- **`streammerge.log`**：完整的程序运行日志（ffmpeg 生命周期、健康检查、错误等）
- **`{output-dir}/ffmpeg.log`**：ffmpeg 的 stderr 输出

## 输出文件

输出目录中生成的文件：

```
output/
├── index.m3u8        # HLS 播放列表（主入口）
├── index0.ts         # TS 视频分片
├── index1.ts
├── ...
└── ffmpeg.log        # ffmpeg 运行日志

streammerge.log       # 程序运行日志（工作目录下）
```

### 播放输出流

**本地播放（VLC）：**

```bash
vlc ./output/index.m3u8
```

**局域网播放（需开启 HTTP 服务）：**

```bash
vlc http://192.168.1.100:8080/index.m3u8
```

**浏览器播放（使用 hls.js 等播放器）：**

```html
<video id="player"></video>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
  const video = document.getElementById('player');
  const hls = new Hls({ lowLatencyMode: true });
  hls.loadSource('http://localhost:8080/index.m3u8');
  hls.attachMedia(video);
</script>
```

## LL-HLS 低延迟

默认启用 LL-HLS 模式，参数如下：

- 分片时长：1 秒
- 播放列表大小：5 个分片
- 独立分片：每个分片可独立解码
- 端到端延迟：约 2-3 秒

`hls_list_size=5` 意味着每个 TS 分片在播放列表中存留约 5 秒后被自动删除。

## 容错机制

| 故障 | 处理方式 |
|------|----------|
| 输入流中断 | ffmpeg 自动重连（5 秒重试间隔） |
| ffmpeg 进程崩溃 | 2 秒后自动重启，最多连续重试 5 次 |
| 输出磁盘满 | 清理旧分片后重试，仍然失败则优雅退出 |
| 输入流编码变更 | ffmpeg 自适应处理，连续失败则重启 |

## TS 分片清理

三重清理机制确保磁盘不被打满：

1. **ffmpeg 自动清理**：每写入新分片时删除 playlist 中已移除的旧分片
2. **启动清理**：ffmpeg 启动前清空输出目录中的残留 `.ts` / `.m3u8` 文件
3. **定时巡检**（每 60 秒）：若 `.ts` 文件数超过 10 个（`hls_list_size * 2`），删除最旧的多余文件

## 日志

- stdout：结构化日志，带时间戳和级别
- ffmpeg stderr：重定向到 `{output-dir}/ffmpeg.log`

## 常见问题

### Q: 如何知道偏移应该设多少？

先设 `--offset=0ms` 启动，边看输出边用 `←` `→` 键微调到音画同步。记下最终的偏移值，下次直接作为 `--offset` 参数传入。

### Q: 可以同时使用两条流的音频吗？

当前版本仅支持视频来自一条流、音频来自另一条流。同时混音是后续计划的功能。

### Q: 输入流必须是 HTTP(S) 吗？

是的，当前只支持 HLS over HTTP(S)。后续计划支持 SRT 和 RTMP。

### Q: HTTP 服务器端口被占用怎么办？

换一个端口号：`--port 9090`。

### Q: 可以后台运行吗？

```bash
nohup ./streammerge --stream-a ... --stream-b ... > streammerge.log 2>&1 &
```

## 项目结构

```
stream_merge/
├── __init__.py          # 包声明
├── __main__.py          # python -m 入口
├── cli.py               # CLI 参数解析与主入口
├── offset.py            # 时间偏移解析与格式化
├── command.py           # ffmpeg 命令构建
├── stream_manager.py    # ffmpeg 进程生命周期管理
├── controller.py        # 交互式键盘控制
├── server.py            # HTTP 静态文件服务
└── monitor.py           # 健康监控与分片清理

tests/
├── __init__.py
├── test_cli.py
├── test_offset.py
├── test_command.py
└── test_integration.py

docs/superpowers/
├── specs/2026-07-07-stream-merge-design.md
└── plans/2026-07-07-stream-merge-plan.md

streammerge             # 便捷启动脚本
```
