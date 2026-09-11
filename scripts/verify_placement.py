"""Opt-in live test in a disposable project; restores the original project.

Run from the project root: .venv/bin/python -m scripts.verify_placement SAMPLE.mp4
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
        metadata = dict(project_id=temporary.GetUniqueId(), timeline_id=timeline.GetUniqueId())
        from vincisub.placement import place
        from vincisub.storage import write_json
        timeline.SetStartTimecode('01:00:00:00')
        identity = timeline.GetUniqueId()
        def state():
            return [(kind,n,i.GetUniqueId(),i.GetStart(),i.GetEnd())
                    for kind in ('video','audio') for n in range(1,timeline.GetTrackCount(kind)+1)
                    for i in timeline.GetItemListInTrack(kind,n)]
        timeline.AddTrack('subtitle')
        seed = output/'existing.srt'
        seed.write_text('1\n00:00:00,000 --> 00:00:01,000\n保留原有字幕\n', encoding='utf-8-sig')
        seed_media = import_media(pool, seed)
        pool.AppendToTimeline([dict(mediaPoolItem=seed_media[0],trackIndex=1)])
        existing = [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',1)]
        before = state()
        write_json(output/'resolve.json', metadata)
        rows = [dict(start=.12,end=1.12,text='第一条字幕'),dict(start=2.2,end=3.6,text='第二条字幕'),dict(start=5,end=7.6,text='第三条字幕')]
        write_json(output/'result.json', dict(captions=rows,duration=8.68,offset=0))
        track = place(output, resolve)
        captions = timeline.GetItemListInTrack('subtitle',track)
        assert [(i.GetName(),i.GetStart(),i.GetEnd()) for i in captions] == [(c['text'],90000+round(c['start']*25),90000+round(c['end']*25)) for c in rows]
        assert state() == before
        assert existing == [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',1)]
        assert track == 2
        assert temporary.GetCurrentTimeline().GetUniqueId() == identity
        assert place(output, resolve) == track
        assert timeline.GetTrackCount('subtitle') == track
        print(json.dumps(dict(automatic_placement=True, same_timeline=True, original_media_unchanged=True, duplicate_prevented=True, captions=len(rows))))
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
