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
        assert len(existing) == 1 and existing[0][3] == '保留原有字幕', 'Existing subtitle fixture was not created'
        before = state()
        write_json(output/'resolve.json', metadata)
        rows = [dict(start=.12,end=1.12,text='第一条字幕'),dict(start=2.2,end=3.6,text='第二条字幕'),dict(start=5,end=7.6,text='第三条字幕')]
        write_json(output/'result.json', dict(captions=rows,duration=8.68,offset=0))
        timeline.SetCurrentTimecode('01:00:06:00')
        old_time, old_page = timeline.GetCurrentTimecode(), resolve.GetCurrentPage()
        track = place(output, resolve)
        assert timeline.GetCurrentTimecode() == old_time
        assert resolve.GetCurrentPage() == old_page
        captions = timeline.GetItemListInTrack('subtitle',track)
        assert [(i.GetName(),i.GetStart(),i.GetEnd()) for i in captions] == [(c['text'],90000+round(c['start']*25),90000+round(c['end']*25)) for c in rows]
        assert state() == before
        assert existing == [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',1)]
        assert track == 2
        assert temporary.GetCurrentTimeline().GetUniqueId() == identity
        assert place(output, resolve) == track
        assert timeline.GetTrackCount('subtitle') == track
        from vincisub.editing import sync
        old_ids = [i.GetUniqueId() for i in captions]
        rows[0] = dict(start=.2,end=1.2,text='在插件里修改后的字幕')
        write_json(output/'result.json',dict(captions=rows,duration=8.68,offset=0))
        assert sync(output,resolve) == track
        updated = timeline.GetItemListInTrack('subtitle',track)
        assert [(i.GetName(),i.GetStart(),i.GetEnd()) for i in updated] == [(c['text'],90000+round(c['start']*25),90000+round(c['end']*25)) for c in rows]
        assert [i.GetName() for i in updated][1:] == [c['text'] for c in rows][1:]
        assert timeline.GetTrackCount('subtitle') == track
        assert state() == before
        assert existing == [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',1)]
        # Simulate an API append refusal after deletion; real restoration must succeed.
        class Proxy:
            def __init__(self, wrapped, **overrides):
                self.wrapped, self.overrides = wrapped, overrides
            def __getattr__(self,key):
                return self.overrides.get(key,getattr(self.wrapped,key))
        calls = [0]
        def refuse_once(media):
            calls[0] += 1
            return [] if calls[0] == 1 else pool.AppendToTimeline(media)
        wrapped_pool = Proxy(pool,AppendToTimeline=refuse_once)
        wrapped_project = Proxy(temporary,GetMediaPool=lambda:wrapped_pool)
        wrapped_manager = Proxy(manager,GetCurrentProject=lambda:wrapped_project)
        wrapped_resolve = Proxy(resolve,GetProjectManager=lambda:wrapped_manager)
        failed_rows = [dict(r) for r in rows]
        failed_rows[0]['text'] = '这次更新应失败并恢复'
        write_json(output/'result.json',dict(captions=failed_rows,duration=8.68,offset=0))
        try:
            sync(output,wrapped_resolve)
            raise AssertionError('Expected a refused update')
        except RuntimeError as error:
            assert '同步后的' in str(error), str(error)
        restored = timeline.GetItemListInTrack('subtitle',track)
        assert [(i.GetName(),i.GetStart(),i.GetEnd()) for i in restored] == [(c['text'],90000+round(c['start']*25),90000+round(c['end']*25)) for c in rows]
        assert state() == before
        # Simulate external editing: all clip IDs change and an extra caption is added.
        from vincisub.subtitles import Caption, to_srt
        rows.append(dict(start=7.8,end=8.2,text='在时间线额外补充的字幕'))
        manual = output/'manual-edit.srt'
        manual.write_text(to_srt([Caption(**r) for r in rows]),encoding='utf-8-sig')
        manual_media = import_media(pool,manual)
        assert timeline.DeleteClips(timeline.GetItemListInTrack('subtitle',track),False)
        pool.AppendToTimeline(manual_media)
        import time
        time.sleep(.5)
        assert len(timeline.GetItemListInTrack('subtitle',track)) == 4
        # A second selection in an earlier gap must reuse the same track.
        second_job = output.parent/(name+'_second')
        second_job.mkdir()
        write_json(second_job/'resolve.json',dict(metadata,start=90030,end=90055))
        later_rows = [dict(start=1.4,end=2,text='第二次选区')]
        write_json(second_job/'result.json',dict(captions=later_rows,duration=8.68,offset=0))
        assert place(second_job,resolve) == track
        assert timeline.GetTrackCount('subtitle') == track
        combined = sorted(rows+later_rows,key=lambda r:r['start'])
        def contents():
            return [(i.GetName(),i.GetStart(),i.GetEnd()) for i in timeline.GetItemListInTrack('subtitle',track)]
        def expected(values):
            return [(r['text'],90000+round(r['start']*25),90000+round(r['end']*25)) for r in sorted(values,key=lambda r:r['start'])]
        assert contents() == expected(combined)
        assert place(second_job,resolve) == track
        later_rows[0]['text'] = '只修改第二次字幕'
        write_json(second_job/'result.json',dict(captions=later_rows,duration=8.68,offset=0))
        assert sync(second_job,resolve) == track
        assert contents() == expected(rows+later_rows)
        # Overlapping selection creates a new track without overwriting the reused track.
        overlap_job = output.parent/(name+'_overlap')
        overlap_job.mkdir()
        write_json(overlap_job/'resolve.json',dict(metadata,start=90035,end=90050))
        write_json(overlap_job/'result.json',dict(captions=[dict(start=1.5,end=1.9,text='重叠选区')],duration=8.68,offset=0))
        assert place(overlap_job,resolve) == track+1
        assert contents() == expected(rows+later_rows)
        assert state() == before
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
