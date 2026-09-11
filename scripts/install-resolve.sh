#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
scripts_dir="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$scripts_dir"
ln -s "$project_root/scripts/VinciSub.py" "$scripts_dir/VinciSub.py"
echo "已添加 VinciSub 启动脚本。重启达芬奇后，在 工作区 → 脚本 → Utility 中打开。"
