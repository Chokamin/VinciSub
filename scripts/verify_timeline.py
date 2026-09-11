"""Live read-only audio extraction test in a disposable Resolve project."""
import json
import sys
import time
import uuid
from pathlib import Path

from vincisub.resolve import connect, import_media
from vincisub.timeline import selection, snapshot, decode


def main():
    from vincisub.storage import DATA
    vocabulary_path = DATA/"vocabulary.json"
    reference_path = DATA/"reference-script.json"
    reference_before = reference_path.read_bytes() if reference_path.exists() else None
    vocabulary_before = vocabulary_path.read_bytes() if vocabulary_path.exists() else None
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
        both = snapshot(resolve, [1, 2])
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
        ui.QueueEvent(widgets['VocabularySettings'],'Clicked',{})
        time.sleep(.3)
        vocabulary_window=ui.FindWindow('com.vincisub.native.vocabulary')
        vocabulary_widgets=vocabulary_window.GetItems()
        vocabulary_widgets['Vocabulary'].PlainText = '中文字幕工具，中文字幕工具'
        vocabulary_widgets['UseVocabulary'].Checked = True
        ui.QueueEvent(vocabulary_widgets['SaveVocabulary'],'Clicked',{})
        time.sleep(.3)
        assert json.loads(vocabulary_path.read_text(encoding='utf-8'))['terms'] == ['中文字幕工具']
        ui.QueueEvent(widgets['ReferenceScript'],'Clicked',{});time.sleep(.3)
        reference_widgets=ui.FindWindow('com.vincisub.native.reference').GetItems()
        reference_widgets['Script'].PlainText='欢迎使用中文字幕工具。今天我们测试字幕识别。口播结束后去月球旅行。'
        reference_widgets['UseScript'].Checked=True
        ui.QueueEvent(reference_widgets['SaveScript'],'Clicked',{});time.sleep(.2)
        ui.QueueEvent(widgets['ReferenceScript'],'Clicked',{});time.sleep(.2)
        assert '去月球旅行' in reference_widgets['Script'].PlainText
        reference_widgets['Script'].PlainText='取消不能覆盖'
        ui.QueueEvent(reference_widgets['CancelScript'],'Clicked',{});time.sleep(.2)
        assert widgets['Track'].TopLevelItemCount() == 2
        assert all(widgets['Track'].TopLevelItem(n).CheckState[0] == 'Unchecked' for n in range(2))
        for n in range(2):
            widgets['Track'].TopLevelItem(n).CheckState[0] = 'Checked'
        ui.QueueEvent(widgets['Refresh'], 'Clicked', {})
        time.sleep(.5)
        assert all(widgets['Track'].TopLevelItem(n).CheckState[0] == 'Checked' for n in range(2))
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
        assert request['timeline']['track_indices'] == [1, 2]
        assert request['vocabulary'] == ['中文字幕工具']
        assert '去月球旅行' in request['reference_script']
        result = json.loads((job/'result.json').read_text(encoding='utf-8'))
        assert all(1 <= row['start'] < row['end'] <= 5.001 for row in result['captions']), result
        assert not (job/'audio.wav').exists() and not (job/'source').exists()
        time.sleep(1)
        assert widgets['Captions'].TopLevelItemCount() == len(result['captions'])
        deadline = time.monotonic() + 180
        placement = {}
        while time.monotonic() < deadline:
            if (job/'placement.json').exists():
                placement = json.loads((job/'placement.json').read_text(encoding='utf-8'))
                if placement['state'] in ('done','error'):
                    break
            time.sleep(.5)
        assert placement.get('state') == 'done', placement
        assert temporary.GetCurrentTimeline().GetUniqueId() == second['timeline_id']
        subtitles = timeline.GetItemListInTrack('subtitle', timeline.GetTrackCount('subtitle'))
        assert len(subtitles) == len(result['captions'])
        for item, caption in zip(subtitles, result['captions']):
            assert item.GetStart() == 90000 + round(caption['start']*25)
            assert item.GetEnd() == 90000 + round(caption['end']*25)
        time.sleep(1)
        assert '月球' not in ''.join(c['text'] for c in result['captions'])
        original_second = (subtitles[1].GetName(),subtitles[1].GetStart(),subtitles[1].GetEnd())
        track_count = timeline.GetTrackCount('subtitle')
        assert 'Text' not in widgets and 'Apply' not in widgets and 'Offset' not in widgets
        widgets['Captions'].TopLevelItem(0).Selected = True
        ui.QueueEvent(widgets['Captions'],'ItemDoubleClicked',{})
        time.sleep(.5)
        editor=ui.FindWindow('com.vincisub.native.editor')
        edit_widgets=editor.GetItems()
        assert edit_widgets['Text'].PlainText == result['captions'][0]['text'], 'Subtitle row selection did not reach editor: '+str(widgets['Status'].Text)
        assert not window.Enabled
        edit_widgets['Text'].PlainText = '取消的修改不能保存'
        ui.QueueEvent(edit_widgets['CancelEdit'],'Clicked',{});time.sleep(.2)
        assert window.Enabled
        ui.QueueEvent(widgets['Captions'],'ItemDoubleClicked',{});time.sleep(.2)
        assert edit_widgets['Text'].PlainText == result['captions'][0]['text']
        edit_widgets['End'].Value = 0
        ui.QueueEvent(edit_widgets['Apply'],'Clicked',{});time.sleep(.2)
        assert edit_widgets['EditStatus'].Text and not window.Enabled
        edit_widgets['End'].Value = result['captions'][0]['end']
        edit_widgets['Text'].PlainText = '在插件里校对的字幕'
        ui.QueueEvent(edit_widgets['Apply'],'Clicked',{})
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            time.sleep(.5)
            current=timeline.GetItemListInTrack('subtitle',track_count)
            if current and current[0].GetName() == '在插件里校对的字幕':
                break
        assert current[0].GetName() == '在插件里校对的字幕'
        assert (current[1].GetName(),current[1].GetStart(),current[1].GetEnd()) == original_second
        assert timeline.GetTrackCount('subtitle') == track_count
        time.sleep(1)
        # Generate a second non-overlapping selection through the same native window.
        first_contents = [(i.GetStart(),i.GetEnd(),i.GetName()) for i in current]
        # Reproduce manual timeline edits that invalidate old receipts.
        from vincisub.subtitles import Caption, to_srt
        manual_rows=[Caption(.1,.5,'手动补充，必须保留')]+[Caption((a-90000)/25,(b-90000)/25,text) for a,b,text in first_contents]
        manual=job/'manual-test.srt'
        manual.write_text(to_srt(manual_rows),encoding='utf-8-sig')
        manual_media=import_media(temporary.GetMediaPool(),manual)
        assert timeline.DeleteClips(current,False)
        temporary.GetMediaPool().AppendToTimeline(manual_media)
        time.sleep(.5)
        current=timeline.GetItemListInTrack('subtitle',track_count)
        first_contents=[(i.GetStart(),i.GetEnd(),i.GetName()) for i in current]
        assert len(first_contents)==len(manual_rows)
        assert first_contents[0][2]=='手动补充，必须保留'

        timeline.SetMarkInOut(125,216)
        widgets['Track'].TopLevelItem(1).CheckState[0] = 'Unchecked'
        ui.QueueEvent(widgets['VocabularySettings'],'Clicked',{})
        time.sleep(.3)
        assert vocabulary_widgets['Vocabulary'].PlainText == '中文字幕工具'
        vocabulary_widgets['Vocabulary'].PlainText = '不应该保存'
        ui.QueueEvent(vocabulary_widgets['CancelVocabulary'],'Clicked',{})
        time.sleep(.3)
        assert json.loads(vocabulary_path.read_text(encoding='utf-8'))['terms'] == ['中文字幕工具']
        ui.QueueEvent(widgets['VocabularySettings'],'Clicked',{})
        time.sleep(.3)
        vocabulary_widgets['UseVocabulary'].Checked = False
        ui.QueueEvent(vocabulary_widgets['SaveVocabulary'],'Clicked',{})
        time.sleep(.3)
        ui.QueueEvent(widgets['ReferenceScript'],'Clicked',{});time.sleep(.2)
        reference_widgets['UseScript'].Checked=False
        ui.QueueEvent(reference_widgets['SaveScript'],'Clicked',{});time.sleep(.2)
        previous_job = job
        ui.QueueEvent(widgets['Generate'],'Clicked',{})
        deadline = time.monotonic()+150
        second_placement = {}
        while time.monotonic()<deadline:
            time.sleep(.5)
            latest=json.loads((DATA/'native-latest.json').read_text(encoding='utf-8'))['id']
            job=DATA/'jobs'/latest
            if job == previous_job:
                continue
            if (job/'placement.json').exists():
                second_placement=json.loads((job/'placement.json').read_text(encoding='utf-8'))
                if second_placement['state'] in ('done','error'):
                    break
            worker_status=json.loads((job/'status.json').read_text(encoding='utf-8'))
            assert worker_status['state'] not in ('error','cancelled'),worker_status
        assert second_placement.get('state') == 'done',second_placement
        assert json.loads((job/'request.json').read_text(encoding='utf-8'))['vocabulary'] == []
        assert json.loads((job/'request.json').read_text(encoding='utf-8'))['reference_script'] == ''
        assert timeline.GetTrackCount('subtitle') == track_count
        final_contents=[(i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',track_count)]
        assert final_contents[:len(first_contents)] == first_contents
        assert len(final_contents)>len(first_contents)
        assert all(start>=90125 for start,end,text in final_contents[len(first_contents):])
        time.sleep(1)
        # Scan every track, including an overlapping disabled subtitle track.
        assert timeline.AddTrack('subtitle')
        other_track=timeline.GetTrackCount('subtitle')
        timeline.SetTrackEnable('subtitle',track_count,False)
        timeline.SetTrackEnable('subtitle',other_track,True)
        time.sleep(.3)
        other_srt=job/'other-track.srt'
        other_srt.write_text(to_srt([Caption(.2,.6,'另一条轨道')]),encoding='utf-8-sig')
        temporary.GetMediaPool().AppendToTimeline(import_media(temporary.GetMediaPool(),other_srt))
        time.sleep(.3)
        timeline.SetTrackEnable('subtitle',other_track,False)
        timeline.SetTrackEnable('subtitle',track_count,True)
        other_before=[(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',other_track)]
        assert len(other_before)==1
        ui.QueueEvent(widgets['ReadAll'],'Clicked',{})
        time.sleep(1)
        assert widgets['Captions'].TopLevelItemCount()==len(final_contents)+1
        assert widgets['Captions'].TopLevelItem(1).Text[4]==f'ST{other_track}'
        assert '已读取全部' in widgets['Status'].Text,widgets['Status'].Text
        widgets['Captions'].TopLevelItem(0).Selected=True
        ui.QueueEvent(widgets['Captions'],'ItemDoubleClicked',{})
        time.sleep(.3)
        edit_widgets['Text'].PlainText='从全部字幕列表修改'
        ui.QueueEvent(edit_widgets['Apply'],'Clicked',{})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            time.sleep(.5)
            refreshed=timeline.GetItemListInTrack('subtitle',track_count)
            if refreshed and refreshed[0].GetName()=='从全部字幕列表修改' and not widgets['Cancel'].Enabled:
                break
        assert refreshed[0].GetName()=='从全部字幕列表修改'
        assert other_before==[(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',other_track)]
        from vincisub.optimize import optimize
        from vincisub.catalog import read_all
        before_opt=read_all(resolve)
        expected=optimize(before_opt['tracks'][track_count]['captions'],all_punctuation=True,fill_gaps=True,max_gap=.5)
        ui.QueueEvent(widgets['Optimize'],'Clicked',{});time.sleep(.3)
        opt=ui.FindWindow('com.vincisub.native.optimize').GetItems()
        opt['OptimizeTrack'].CurrentIndex=track_count-1
        opt['StripPunctuation'].Checked=True;opt['FillGaps'].Checked=True
        ui.QueueEvent(opt['FillGaps'],'Clicked',{});time.sleep(.2)
        assert '将修改' in opt['OptimizeStatus'].Text,opt['OptimizeStatus'].Text
        ui.QueueEvent(opt['CancelOptimize'],'Clicked',{});time.sleep(.2)
        assert read_all(resolve)['rows']==before_opt['rows']
        ui.QueueEvent(widgets['Optimize'],'Clicked',{});time.sleep(.2)
        opt['OptimizeTrack'].CurrentIndex=track_count-1
        ui.QueueEvent(opt['ApplyOptimize'],'Clicked',{})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            time.sleep(.5)
            actual=read_all(resolve)['tracks'][track_count]['captions']
            if actual==expected and not widgets['Cancel'].Enabled:break
        assert actual==expected,(actual,expected)
        assert other_before==[(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in timeline.GetItemListInTrack('subtitle',other_track)]

        assert timeline.GetTrackCount('subtitle')==other_track
        time.sleep(1)
        assert widgets['Captions'].TopLevelItemCount()==len(final_contents)+1
        ui.QueueEvent(window, 'Close', {'close':True})
        deadline = time.monotonic()+5
        while ui.FindWindow('com.vincisub.native') and time.monotonic()<deadline:
            time.sleep(.1)
        assert not ui.FindWindow('com.vincisub.native'), 'Closed window was not retired'
        window = None
        timeline.ClearMarkInOut()
        assert selection(timeline)['duration'] == full['duration']
        print(json.dumps(dict(full=full, marked=marked, samples=len(audio), clips=plan['clips'], no_render_jobs=not temporary.GetRenderJobList(), native_asr=result), ensure_ascii=False))
    finally:
        if window:
            ui.QueueEvent(window.GetItems()['Cancel'], 'Clicked', {})
            time.sleep(1)
            ui.QueueEvent(window, 'Close', {'close':True})
        if reference_before is None:
            reference_path.unlink(missing_ok=True)
        else:
            reference_path.write_bytes(reference_before)
        if vocabulary_before is None:
            vocabulary_path.unlink(missing_ok=True)
        else:
            vocabulary_path.write_bytes(vocabulary_before)
        manager.CloseProject(temporary)
        if not manager.LoadProject(name):
            raise RuntimeError('Could not restore original project')
        resolve.OpenPage(page)
        if temporary_name in manager.GetProjectListInCurrentFolder():
            manager.DeleteProject(temporary_name)


if __name__ == '__main__':
    main()
