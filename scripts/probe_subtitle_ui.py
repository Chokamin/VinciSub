"""Opt-in UI positioning verification in a disposable Resolve project.

Run: .venv/bin/python -m scripts.probe_subtitle_ui SAMPLE.mp4
After READY, use Resolve UI / CUA to insert the imported SRT in a subtitle
track. The successful tested route adds that track and appends the SRT via
API WITHOUT source frame bounds, selects the first subtitle, then edits its
Inspector start/end to 01:00:02:00 / 01:00:03:00. Use Next and set the second
to 01:00:05:00 / 01:00:06:00. Use a 25 fps sample.

This harness only verifies the outcome. It does NOT implement standalone UI
automation for VinciSub. It checks the same timeline and unchanged audio/video,
then restores the saved original project and deletes the disposable project.
"""

import argparse
import json
import uuid
from pathlib import Path

from vincisub.resolve import connect, import_media


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
        import time
        timeline.SetStartTimecode('01:00:00:00')
        timeline.SetCurrentTimecode('01:00:00:00')
        identity = timeline.GetUniqueId()
        def media_state():
            return [(kind, n, i.GetUniqueId(), i.GetStart(), i.GetEnd())
                    for kind in ('video', 'audio')
                    for n in range(1, timeline.GetTrackCount(kind)+1)
                    for i in timeline.GetItemListInTrack(kind, n)]
        before = media_state()
        srt = output / 'UI_SUBTITLE_TEST.srt'
        srt.write_text('1\n00:00:02,000 --> 00:00:03,000\n第一条定位验证\n\n2\n00:00:05,000 --> 00:00:06,000\n第二条定位验证\n', encoding='utf-8-sig')
        assert import_media(pool, srt)
        resolve.OpenPage('edit')
        print('READY', name, str(srt), flush=True)
        previous_rows = None
        for _ in range(240):
            time.sleep(1)
            rows = [(i.GetName(), i.GetStart(), i.GetEnd())
                    for n in range(1, timeline.GetTrackCount('subtitle')+1)
                    for i in timeline.GetItemListInTrack('subtitle', n)]
            if len(rows) == 2:
                if rows != previous_rows:
                    print('SUBTITLES', rows, flush=True)
                    previous_rows = rows
                if rows == [('第一条定位验证',90050,90075),('第二条定位验证',90125,90150)]:
                    assert identity == temporary.GetCurrentTimeline().GetUniqueId()
                    assert before == media_state(), 'Audio/video changed'
                    print('PASS: same timeline, exact subtitle positions, audio/video unchanged', flush=True)
                    break
            if (output/'stop').exists():
                raise AssertionError('Stopped without passing')
        else:
            raise AssertionError('UI validation timed out')
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
