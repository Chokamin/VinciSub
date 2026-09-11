import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vincisub.placement import frame_rows, place, reusable_job


@patch('vincisub.placement.time.sleep')
class PlacementTests(unittest.TestCase):
    def scene(self, directory):
        r, p, t = MagicMock(), MagicMock(), MagicMock()
        r.GetProjectManager.return_value.GetCurrentProject.return_value = p
        p.GetCurrentTimeline.return_value = t
        p.GetUniqueId.return_value, t.GetUniqueId.return_value = 'p', 't'
        r.GetVersion.return_value = [21, 1]
        t.GetSetting.return_value = 25
        t.GetCurrentTimecode.return_value = '01:00:07:00'
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 90000, 90250
        t.GetTrackCount.return_value = 1
        t.GetTrackName.return_value = 'VinciSub ' + directory.name[:8]
        t.GetIsTrackEnabled.return_value = True
        result = dict(duration=10, offset=.04, captions=[dict(start=2,end=3,text='甲'), dict(start=5,end=6,text='乙')])
        (directory/'result.json').write_text(json.dumps(result), encoding='utf-8')
        (directory/'resolve.json').write_text(json.dumps(dict(project_id='p',timeline_id='t')), encoding='utf-8')
        items = []
        for n, row in enumerate(result['captions']):
            i = MagicMock()
            i.GetUniqueId.return_value = str(n)
            i.GetName.return_value = row['text']
            i.GetStart.return_value = 90001 + row['start']*25
            i.GetEnd.return_value = 90001 + row['end']*25
            items.append(i)
        tracks = {1: [], 2: []}
        def append(media):
            tracks[2].extend(items)
            return items
        p.GetMediaPool.return_value.AppendToTimeline.side_effect = append
        t.GetItemListInTrack.side_effect = lambda kind, index: tracks[index]
        return r, p, t, items, tracks

    def test_frame_quantization_and_nonzero_start(self, sleep):
        t = MagicMock()
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 90000,90250
        fps, rows = frame_rows(dict(captions=[dict(start=2.04,end=3.04,text='你好')]),t)
        self.assertEqual((fps, rows[0]['start'], rows[0]['end']), (25,90051,90076))

    def test_rejects_collapsed_caption(self, sleep):
        t = MagicMock()
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 0,250
        with self.assertRaises(ValueError):
            frame_rows(dict(captions=[dict(start=2,end=2.001,text='甲')]),t)

    def test_wrong_timeline_and_cancel_fail_before_mutation(self, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.scene(d)
            p.GetUniqueId.return_value = 'wrong'
            with self.assertRaises(ValueError): place(d,r)
            p.GetUniqueId.return_value = 'p'
            (d/'placement-cancel').touch()
            with self.assertRaisesRegex(RuntimeError,'取消'): place(d,r)
            t.AddTrack.assert_not_called()

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_bulk_media_list_srt_offset_and_duplicate_prevention(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.scene(d)
            self.assertEqual(place(d,r),2)
            p.GetMediaPool.return_value.AppendToTimeline.assert_called_once_with(imported.return_value)
            srt = imported.call_args.args[1].read_text(encoding='utf-8-sig')
            self.assertIn('00:00:02,040 --> 00:00:03,040',srt)
            self.assertIn('00:00:05,040 --> 00:00:06,040',srt)
            self.assertEqual(place(d,r),2)
            t.AddTrack.assert_called_once()
            t.DeleteTrack.assert_not_called()
            r.OpenPage.assert_not_called()
            t.SetCurrentTimecode.assert_called_once_with('01:00:07:00')
            self.assertEqual([c.args for c in t.SetTrackEnable.call_args_list], [('subtitle',1,False),('subtitle',2,True)])

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_bad_position_rolls_back_new_track(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,items,_ = self.scene(d)
            items[0].GetStart.return_value += 250
            with self.assertRaisesRegex(RuntimeError,'回读验证失败'): place(d,r)
            t.DeleteTrack.assert_called_once_with('subtitle',2)
            t.SetTrackEnable.assert_any_call('subtitle',1,True)
            self.assertFalse((d/'placement-receipt.json').exists())

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_wrong_track_removes_only_new_captions(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,items,tracks = self.scene(d)
            old = MagicMock(); old.GetUniqueId.return_value = 'existing'
            tracks[1].append(old)
            p.GetMediaPool.return_value.AppendToTimeline.side_effect = lambda _: tracks[1].extend(items)
            with self.assertRaisesRegex(RuntimeError,'回读验证失败'): place(d,r)
            t.DeleteClips.assert_called_once_with(items,False)
            t.DeleteTrack.assert_called_once_with('subtitle',2)

    @patch('vincisub.placement.import_media', return_value=[])
    def test_import_failure_restores_old_track(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.scene(d)
            with self.assertRaisesRegex(RuntimeError,'导入字幕'): place(d,r)
            p.GetMediaPool.return_value.AppendToTimeline.assert_not_called()
            t.SetTrackEnable.assert_any_call('subtitle',1,True)
            t.DeleteTrack.assert_called_once()

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_append_exception_after_write_is_cleaned(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,items,tracks = self.scene(d)
            def append(_):
                tracks[2].extend(items)
                raise RuntimeError('IPC interrupted')
            p.GetMediaPool.return_value.AppendToTimeline.side_effect = append
            with self.assertRaisesRegex(RuntimeError,'追加失败'): place(d,r)
            t.DeleteTrack.assert_called_once()
            self.assertFalse((d/'placement-receipt.json').exists())

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_changed_written_result_cannot_duplicate(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.scene(d)
            place(d,r)
            result = json.loads((d/'result.json').read_text(encoding='utf-8'))
            result['captions'][0]['text'] = '修改'
            (d/'result.json').write_text(json.dumps(result),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'写入记录'): place(d,r)
            p.GetMediaPool.return_value.AppendToTimeline.assert_called_once()

    def test_reuse_checks_selection_boundaries_identity_and_lock(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';old.mkdir();new=root/'new';new.mkdir()
            r,p,t,items,tracks=self.scene(old)
            tracks[1]=items
            t.GetIsTrackLocked.return_value=False
            metadata=dict(project_id='p',timeline_id='t',start=90076,end=90126)
            receipt=dict(track=1,items=[(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in items])
            (old/'placement-receipt.json').write_text(json.dumps(receipt))
            rows=[dict(start=90100,end=90110,text='新')]
            self.assertEqual(reusable_job(new,metadata,t,rows),new/'reuse-source')
            self.assertIsNone(reusable_job(new,dict(metadata,start=90075),t,rows))
            self.assertIsNone(reusable_job(new,dict(metadata,timeline_id='other'),t,rows))
            t.GetIsTrackLocked.return_value=True
            self.assertIsNone(reusable_job(new,metadata,t,rows))
            t.GetIsTrackLocked.return_value=False
            items[0].GetName.return_value='外部修改'
            self.assertEqual(reusable_job(new,metadata,t,rows),new/'reuse-source')
            fresh=json.loads((new/'reuse-source'/'placement-receipt.json').read_text(encoding='utf-8'))
            self.assertEqual(fresh['items'][0][3],'外部修改')

    def test_reuse_searches_past_conflicting_track_and_preserves_live_extra_caption(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';old.mkdir();new=root/'new';new.mkdir()
            r,p,t,items,tracks=self.scene(old)
            metadata=dict(project_id='p',timeline_id='t',start=90076,end=90126)
            (old/'placement-receipt.json').write_text(json.dumps(dict(track=1,items=[])))
            t.GetTrackCount.return_value=2
            t.GetIsTrackLocked.return_value=False
            extra=MagicMock();extra.GetUniqueId.return_value='manually-added'
            extra.GetStart.return_value=90190;extra.GetEnd.return_value=90200
            extra.GetName.return_value='手动添加'
            tracks[1]=[items[0],items[1],extra]
            blocked=MagicMock();blocked.GetStart.return_value=90100;blocked.GetEnd.return_value=90110
            tracks[2]=[blocked]
            # Active track conflicts; the disabled track still has a usable gap.
            t.GetIsTrackEnabled.side_effect=lambda kind,n:n==2
            chosen=reusable_job(new,metadata,t,[dict(start=90100,end=90110,text='新')])
            self.assertIsNotNone(chosen)
            receipt=json.loads((chosen/'placement-receipt.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['track'],1)
            self.assertEqual(receipt['items'][-1][3],'手动添加')
            t.GetTrackName.return_value='用户自己的字幕轨'
            self.assertIsNone(reusable_job(new,metadata,t,[dict(start=90100,end=90110,text='新')]))
