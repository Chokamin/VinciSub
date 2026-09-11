#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  echo "请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "请先安装 FFmpeg，macOS 可运行：brew install ffmpeg"
  exit 1
fi
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.lock
echo "依赖安装完成。运行 bash scripts/install-resolve.sh 安装达芬奇脚本入口。"
