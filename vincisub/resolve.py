"""Resolve adapter. Import adds media only; it never guesses a subtitle track API."""

import importlib
import os
import sys
from pathlib import Path


def connect():
    locations = {
        "darwin": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        "win32": "C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules",
        "linux": "/opt/resolve/Developer/Scripting/Modules",
    }
    location = os.environ.get("RESOLVE_SCRIPT_API")
    sys.path.append(str(Path(location) / "Modules") if location else locations.get(sys.platform, ""))
    try:
        module = importlib.import_module("DaVinciResolveScript")
        resolve = module.scriptapp("Resolve")
    except (ImportError, OSError) as error:
        raise RuntimeError("未找到达芬奇脚本接口，请安装 DaVinci Resolve Studio。") from error
    if not resolve:
        raise RuntimeError("无法连接达芬奇。请启动 Studio，并将偏好设置 → 系统 → 常规 → 外部脚本设为本地。")
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError("请先在达芬奇中打开一个项目。")
    return resolve, project


def describe():
    resolve, project = connect()
    timeline = project.GetCurrentTimeline()
    return dict(connected=True, version=resolve.GetVersionString(), project=project.GetName(), timeline=timeline.GetName() if timeline else None)


def import_media(pool, path):
    # 21.1's external Python bridge still needs the documented legacy path list
    # for WAV/SRT on macOS, despite advertising the newer clip-info signature.
    return pool.ImportMedia([{"FilePath": str(path)}]) or pool.ImportMedia([str(path)])


def import_subtitle(path, metadata=None):
    _, project = connect()
    if metadata and project.GetUniqueId() != metadata["project_id"]:
        raise ValueError("当前项目与音频来源不同，请切回原项目后再导入。")
    timeline = project.GetCurrentTimeline()
    if metadata and (not timeline or timeline.GetUniqueId() != metadata["timeline_id"]):
        raise ValueError("当前时间线已变化，请切回生成字幕时的时间线。")
    items = import_media(project.GetMediaPool(), path)
    if not items:
        raise RuntimeError("达芬奇未接受字幕导入。请保存 SRT 后使用 文件 → 导入 → 字幕。")
    return dict(message="字幕已导入媒体池。请将它拖到时间线起点上方，建立字幕轨道。")
