# VinciSub · 奇奇字幕 v0.1.0

首个公开 MVP：在达芬奇原生脚本窗口内完成本地中文字幕识别、校对与同步。

- Qwen3-ASR 本地识别，支持入出点范围、多音轨选择与自动 Solo / Mute 筛选。
- 自动写入原始时间线字幕轨；支持读取全部字幕、双击编辑、原轨同步及 SRT 导出。
- 词库和参考脚本辅助识别；一键优化标点、短间隙、音频对齐及参考脚本校正。
- 模型管理、下载进度、Finder 定位和 GitHub 版本检查。

## 安装

下载下方源码压缩包并解压到固定目录，安装 uv 和 FFmpeg，然后运行：

```sh
bash scripts/setup.sh
bash scripts/install-resolve.sh
```

重启 DaVinci Resolve，在「工作区 → 脚本 → Utility → VinciSub」打开。详细步骤见 README。

## 已验证范围与限制

已实测 Apple Silicon、DaVinci Resolve Studio 21.1、Python 3.12 和 Qwen 0.6B。首次使用需要联网下载模型，模型不包含在发布包中。

这是早期 MVP；其他平台、更多帧率和复杂音频路由仍待验证。源音频读取不复现 Fairlight 效果；字幕同步会重建目标轨中的片段，单条样式应在校对后设置。识别及对齐结果需要人工校对。
