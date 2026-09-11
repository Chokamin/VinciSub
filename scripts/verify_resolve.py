"""Opt-in live test in a disposable project; restores the original project.

Run from the project root: .venv/bin/python -m scripts.verify_resolve SAMPLE.wav
"""

import argparse
import json
import uuid
from pathlib import Path

from vincisub.resolve import connect, import_media, import_subtitle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    if not args.sample.is_file():
        parser.error("样本文件不存在")
    resolve, original = connect()
    manager = resolve.GetProjectManager()
    original_name = original.GetName()
    original_page = resolve.GetCurrentPage()
    if original.IsRenderingInProgress():
        raise RuntimeError("请在渲染结束后验证。")
    if not manager.SaveProject():
        raise RuntimeError("无法保存当前项目，已停止验证。")
    name = "VinciSub_MVP_TEST_" + uuid.uuid4().hex[:8]
    temporary = manager.CreateProject(name)
    if not temporary:
        raise RuntimeError("无法创建独立验证项目。")
    output = Path("/private/tmp") / name
    try:
        output.mkdir(parents=True)
        pool = temporary.GetMediaPool()
        clips = import_media(pool, args.sample.resolve())
        if not clips:
            raise RuntimeError("测试音频无法导入。")
        timeline = pool.CreateTimelineFromClips("VinciSub sample", clips)
        if not timeline:
            raise RuntimeError("无法创建测试时间线。")
        temporary.SetCurrentTimeline(timeline)
        manager.SaveProject()
        metadata = dict(project_id=temporary.GetUniqueId(), timeline_id=timeline.GetUniqueId())
        srt = output / "verification.srt"
        srt.write_text("1\n00:00:00,100 --> 00:00:01,000\n字幕导入验证\n", encoding="utf-8-sig")
        result = import_subtitle(srt, metadata)
        print(json.dumps(dict(import_result=result, temporary_project=True), ensure_ascii=False))
    finally:
        manager.CloseProject(temporary)
        if not manager.LoadProject(original_name):
            raise RuntimeError(f"请手动重新打开原项目：{original_name}")
        if original_page:
            resolve.OpenPage(original_page)
        if name in manager.GetProjectListInCurrentFolder() and not manager.DeleteProject(name):
            raise RuntimeError(f"验证完成，但测试项目需手动删除：{name}")


if __name__ == "__main__":
    main()
