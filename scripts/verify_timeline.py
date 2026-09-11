"""Live read-only audio extraction test in a disposable Resolve project."""
import json
import sys
import time
import uuid
from pathlib import Path

from vincisub.resolve import connect, import_media
from vincisub.timeline import selection, snapshot, decode


def main():
    sample = Path(sys.argv[1]).resolve()
    if not sample.is_file():
        raise ValueError('Missing sample')
    resolve, original = connect()
    manager = resolve.GetProjectManager()
    name, page = original.GetName(), resolve.GetCurrentPage()
    if original.IsRenderingInProgress():
        raise RuntimeError('Wait for render to finish')
    if not manager.SaveProject():
        raise RuntimeError('Cannot save original project')
    temporary_name = 'VinciSub_Range_Test_' + uuid.uuid4().hex[:8]
    temporary = manager.CreateProject(temporary_name)
    if not temporary:
        raise RuntimeError('Cannot create test project')
    window = None
    try:
        media = import_media(temporary.GetMediaPool(), sample)
        timeline = temporary.GetMediaPool().CreateTimelineFromClips('Range test', media)
        temporary.SetCurrentTimeline(timeline)
        timeline.SetStartTimecode('01:00:00:00')
        timeline.AddTrack('audio', 'mono')
        appended = temporary.GetMediaPool().AppendToTimeline([dict(mediaPoolItem=media[0], startFrame=25, endFrame=149, mediaType=2, trackIndex=2, recordFrame=90050)])
        if not appended:
            raise AssertionError('Cannot create second test audio track')
        timeline.SetTrackName('audio', 1, 'First voice')
        timeline.SetTrackName('audio', 2, 'Second voice')
        full = selection(timeline)
        timeline.SetMarkInOut(25, 124)
        marked = selection(timeline)
        plan = snapshot(resolve, 1)
        audio, rate = decode(plan)
        assert abs(marked['duration']-100/marked['fps']) < 1e-6, marked
        assert abs(marked['offset']-25/marked['fps']) < 1e-6, marked
        assert len(audio) == round(marked['duration']*rate)
        assert abs(audio).max() > .001
        second = snapshot(resolve, 2)
        assert second['track_index'] == 2 and len(second['clips']) == 1
        assert abs(second['clips'][0]['offset'] - 1) < .001
        assert abs(second['clips'][0]['source_start'] - 1) < .001
        both = snapshot(resolve)
        assert both['track_indices'] == [1, 2] and len(both['clips']) == 2
        mixed, _ = decode(both)
        import numpy as np
        second_audio, _ = decode(second)
        assert np.allclose(mixed, np.clip(audio + second_audio, -1, 1))
        timeline.SetTrackEnable('audio', 1, False)
        only_second = snapshot(resolve)
        assert only_second['track_indices'] == [2]
        # Exercise the actual native window, worker and automatic result refresh.
        resolve.Fusion().RunScript(str(Path(__file__).resolve().parent / 'VinciSub.py'))
        ui = resolve.Fusion().UIManager
        deadline = time.monotonic() + 15
        window = ui.FindWindow('com.vincisub.native')
        while not window and time.monotonic() < deadline:
            time.sleep(.2)
            window = ui.FindWindow('com.vincisub.native')
        assert window, 'Native window failed to open'
        widgets = window.GetItems()
        assert widgets['Track'].CurrentIndex == 0, 'Default must follow all audible tracks'
        ui.QueueEvent(widgets['Generate'], 'Clicked', {})
        deadline = time.monotonic() + 120
        from vincisub.storage import DATA
        status = {"state": "timeout"}
        while time.monotonic() < deadline:
            time.sleep(.5)
            latest = json.loads((DATA/'native-latest.json').read_text(encoding='utf-8'))['id']
            job = DATA/'jobs'/latest
            request = json.loads((job/'request.json').read_text(encoding='utf-8'))
            if request.get('timeline', {}).get('timeline_id') != second['timeline_id']:
                continue
            status = json.loads((job/'status.json').read_text(encoding='utf-8'))
            if status['state'] in ('done', 'error', 'cancelled'):
                break
        assert status['state'] == 'done', status
        assert request['timeline']['track_indices'] == [2]
        result = json.loads((job/'result.json').read_text(encoding='utf-8'))
        assert all(2 <= row['start'] < row['end'] <= 5.001 for row in result['captions']), result
        assert not (job/'audio.wav').exists() and not (job/'source').exists()
        time.sleep(1)
        assert widgets['Captions'].TopLevelItemCount() == len(result['captions'])
        ui.QueueEvent(widgets['Import'], 'Clicked', {})
        deadline = time.monotonic() + 10
        while '已导入媒体池' not in widgets['Status'].Text and time.monotonic() < deadline:
            time.sleep(.2)
        assert '已导入媒体池' in widgets['Status'].Text, widgets['Status'].Text
        ui.QueueEvent(window, 'Close', {'close':True})
        window = None
        timeline.ClearMarkInOut()
        assert selection(timeline)['duration'] == full['duration']
        print(json.dumps(dict(full=full, marked=marked, samples=len(audio), clips=plan['clips'], no_render_jobs=not temporary.GetRenderJobList(), native_asr=result), ensure_ascii=False))
    finally:
        if window:
            ui.QueueEvent(window.GetItems()['Cancel'], 'Clicked', {})
            time.sleep(1)
            ui.QueueEvent(window, 'Close', {'close':True})
        manager.CloseProject(temporary)
        if not manager.LoadProject(name):
            raise RuntimeError('Could not restore original project')
        resolve.OpenPage(page)
        if temporary_name in manager.GetProjectListInCurrentFolder():
            manager.DeleteProject(temporary_name)


if __name__ == '__main__':
    main()
