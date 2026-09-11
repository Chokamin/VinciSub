# VinciSub

达芬奇原生 Python 脚本，用 Qwen3-ASR 在本机识别中文并生成 SRT。所有操作在达芬奇的脚本窗口中完成，无网页界面或本地 HTTP 服务。

## 当前 MVP

1. 在达芬奇导出需要识别的时间线音频，建议 WAV；静音不需要的轨道。
2. 打开 **工作区 → 脚本 → Utility → VinciSub**。
3. 点击「选择文件」，选择音频或视频，点击「生成字幕」。
4. 点击字幕行修改文字及起止时间，点击「保存当前条」。可调整整体时间偏移。
5. 点击「导入达芬奇」，将媒体池中的 SRT 拖到字幕轨道的对应起点；也可以「保存 SRT」。

当前不自动导出时间线音频，也不自动放置字幕轨道。Resolve 21.1 的自动音频渲染实测未通过，未作为产品入口提供。若音频由整条时间线导出，字幕零点对应时间线起点（包括从 01:00:00:00 开始的时间线），整体偏移通常保持 0。

## 安装（macOS）

已实测：Apple Silicon、DaVinci Resolve Studio 21.1、Python 3.12、Qwen3-ASR-0.6B + Qwen3-ForcedAligner-0.6B，使用 MPS 推理。其他版本及 1.7B 模型尚未实测。

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 FFmpeg（`brew install ffmpeg`），然后在项目目录执行：

```sh
bash scripts/setup.sh
bash scripts/install-resolve.sh
```

重启达芬奇后从脚本菜单打开。需要 Studio 版的 UIManager，并将偏好设置 → 系统 → 常规 → 外部脚本设为「本地」。脚本入口链接到项目目录，移动目录后需重新安装入口；安装程序不会覆盖已有同名入口。

默认使用 0.6B 模型，首次运行会从 Hugging Face 下载识别和时间对齐模型，需网络及数 GB 空间；之后完整缓存可离线使用。音频留在本机，不上传识别服务。模型许可证见 [Qwen3-ASR 官方仓库](https://github.com/QwenLM/Qwen3-ASR)。

## 限制与数据

- 单文件最大 512 MB、最长 30 分钟；长音频按低能量位置分块，边界附近仍可能出现错字或漏字。
- 简体转换、标点恢复、按停顿和字数断句；不支持说话人分离、翻译、字幕样式或实时识别。识别后仍需校对。
- 字幕必须有合法、不重叠的起止时间，偏移后不能早于音频零点。
- 模型、工作音频、结果及任务日志在 `.vincisub/`，不纳入 Git。关闭程序后可按需清理旧的 `jobs/`；保留 `models/` 避免重新下载。
- 任务在独立 Python 进程中执行；取消会结束进程并释放模型内存。关闭窗口前须先取消正在运行的任务。
- 出错时查看对应任务的 `.vincisub/jobs/<任务编号>/worker.log`。

## 开发验证

先阅读 HANDOFF.md、PROJECT_MEMORY.md、DECISIONS.md、CLAUDE.md。

```sh
.venv/bin/python -B -m unittest discover -s tests -v
# 可选：需打开达芬奇；在临时项目验证 SRT 导入，结束后恢复原项目
.venv/bin/python -m scripts.verify_resolve /absolute/path/to/sample.wav
git diff --check
```

原生入口 `scripts/VinciSub.py`；窗口 `vincisub/native_ui.py`；任务控制 `jobs.py`；推理 `worker.py`；字幕规则 `subtitles.py`；达芬奇导入 `resolve.py`。
