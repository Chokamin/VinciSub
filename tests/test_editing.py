import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import test_placement
from vincisub.placement import place
from vincisub.editing import sync


class EditingTests(unittest.TestCase):
    def scene(self,d):
        r,p,t,items,tracks = test_placement.PlacementTests().scene(d)
        with patch('vincisub.placement.import_media',return_value=[object()]), patch('vincisub.placement.time.sleep'):
            place(d,r)
        t.GetTrackCount.return_value=2
        t.GetIsTrackLocked.return_value=False
        def delete(clips,*args):
            for index in tracks:
                tracks[index][:] = [i for i in tracks[index] if i not in clips]
            return True
        t.DeleteClips.side_effect=delete
        result=json.loads((d/'result.json').read_text(encoding='utf-8'))
        result['captions'][0]['text']='修改'
        (d/'result.json').write_text(json.dumps(result),encoding='utf-8')
        return r,p,t,items,tracks

    @patch('vincisub.editing.time.sleep')
    def test_edit_refreshes_same_track_without_duplicate_track(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            new=MagicMock()
            new.GetUniqueId.return_value='updated'
            new.GetName.return_value='修改'
            new.GetStart.return_value=90051;new.GetEnd.return_value=90076
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=lambda _:tracks[2].extend([new,items[1]])
            with patch('vincisub.editing.import_media',return_value=[object()]):
                self.assertEqual(sync(d,r),2)
                self.assertEqual(sync(d,r),2)
            t.DeleteClips.assert_called_once_with(items,False)
            self.assertIn(items[1],tracks[2])
            self.assertEqual(t.AddTrack.call_count,1)

    def test_external_edit_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            items[1].GetName.return_value='在达芬奇修改'
            with self.assertRaisesRegex(ValueError,'外部修改'):sync(d,r)
            t.DeleteClips.assert_not_called()

    @patch('vincisub.editing.time.sleep')
    def test_failed_append_restores_deleted_caption_and_receipt(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            count=[0]
            def append(_):
                count[0]+=1
                if count[0]==1:raise RuntimeError('failed')
                tracks[2].extend(items)
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=append
            with patch('vincisub.editing.import_media',return_value=[object()]):
                with self.assertRaisesRegex(RuntimeError,'failed'):sync(d,r)
            self.assertEqual(set(tracks[2]),set(items))
            receipt=json.loads((d/'placement-receipt.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['items'][0][3],'甲')

    def test_locked_track_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            t.GetIsTrackLocked.return_value=True
            with self.assertRaisesRegex(ValueError,'锁定'):sync(d,r)
            t.DeleteClips.assert_not_called()

    @patch('vincisub.editing.time.sleep')
    def test_partial_delete_failure_restores_whole_track(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            original_delete=t.DeleteClips.side_effect
            count=[0]
            def delete(clips,*args):
                count[0]+=1
                if count[0]==1:
                    tracks[2].remove(items[0])
                    return False
                return original_delete(clips,*args)
            t.DeleteClips.side_effect=delete
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=lambda _:tracks[2].extend(items)
            with patch('vincisub.editing.import_media',return_value=[object()]):
                with self.assertRaisesRegex(RuntimeError,'替换'):sync(d,r)
            self.assertEqual(set(tracks[2]),set(items))

    def test_wrong_project_refuses_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            p.GetUniqueId.return_value='another'
            with self.assertRaisesRegex(ValueError,'原始项目'):sync(d,r)
            t.DeleteClips.assert_not_called()

    @patch('vincisub.editing.time.sleep')
    def test_merge_and_edit_only_current_job_rows(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);d=root/'first';d.mkdir()
            r,p,t,items,tracks=self.scene(d)
            second=root/'second';second.mkdir()
            (second/'resolve.json').write_text((d/'resolve.json').read_text(),encoding='utf-8')
            (second/'result.json').write_text(json.dumps(dict(captions=[dict(start=4,end=4.5,text='新选区')],duration=10)),encoding='utf-8')
            new=MagicMock()
            new.GetUniqueId.return_value='new'
            new.GetName.return_value='新选区'
            new.GetStart.return_value=90100;new.GetEnd.return_value=90113
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=lambda _:tracks[2].extend([items[0],new,items[1]])
            with patch('vincisub.editing.import_media',return_value=[object()]):
                self.assertEqual(sync(second,r,append_from=d),2)
                self.assertEqual(sync(second,r),2)
            receipt=json.loads((second/'placement-receipt.json').read_text())
            self.assertEqual(receipt['owned_indices'],[1])
            self.assertEqual([i.GetName() for i in tracks[2]],['甲','新选区','乙'])
            # Moving the current job into older captions must fail before deletion.
            result=json.loads((second/'result.json').read_text())
            result['captions'][0].update(start=2.5,end=3.5)
            (second/'result.json').write_text(json.dumps(result))
            calls=t.DeleteClips.call_count
            with self.assertRaisesRegex(ValueError,'重叠'):sync(second,r)
            self.assertEqual(t.DeleteClips.call_count,calls)

    @patch('vincisub.editing.time.sleep')
    def test_failed_reuse_restores_source_receipt_without_marking_new_job_done(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);d=root/'first';d.mkdir()
            r,p,t,items,tracks=self.scene(d)
            second=root/'second';second.mkdir()
            (second/'resolve.json').write_text((d/'resolve.json').read_text(),encoding='utf-8')
            (second/'result.json').write_text(json.dumps(dict(captions=[dict(start=4,end=4.5,text='新选区')],duration=10)),encoding='utf-8')
            count=[0]
            def append(_):
                count[0]+=1
                if count[0]==1:raise RuntimeError('reuse failed')
                tracks[2].extend(items)
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=append
            with patch('vincisub.editing.import_media',return_value=[object()]):
                with self.assertRaisesRegex(RuntimeError,'reuse failed'):sync(second,r,append_from=d)
            self.assertFalse((second/'placement-receipt.json').exists())
            receipt=json.loads((d/'placement-receipt.json').read_text())
            self.assertEqual([v[3] for v in receipt['items']],['甲','乙'])
            self.assertEqual(set(tracks[2]),set(items))

    @patch('vincisub.editing.time.sleep')
    def test_reuse_empty_track_without_importing_empty_backup(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);d=root/'first';d.mkdir()
            r,p,t,items,tracks=self.scene(d)
            tracks[2].clear()
            receipt=json.loads((d/'placement-receipt.json').read_text())
            receipt['items']=[]
            (d/'placement-receipt.json').write_text(json.dumps(receipt))
            second=root/'second';second.mkdir()
            (second/'resolve.json').write_text((d/'resolve.json').read_text(),encoding='utf-8')
            result=json.loads((d/'result.json').read_text(encoding='utf-8'))
            result['captions'][0]['text']='甲'
            (second/'result.json').write_text(json.dumps(result),encoding='utf-8')
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=lambda _:tracks[2].extend(items)
            with patch('vincisub.editing.import_media',return_value=[object()]) as imported:
                self.assertEqual(sync(second,r,append_from=d),2)
                imported.assert_called_once()
            t.DeleteClips.assert_not_called()
            t.SetTrackEnable.assert_any_call('subtitle',2,True)

    @patch('vincisub.editing.time.sleep')
    def test_resegmentation_changes_count_only_when_explicit_and_keeps_other_owned_content(self,sleep):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);r,p,t,items,tracks=self.scene(d)
            receipt=json.loads((d/'placement-receipt.json').read_text())
            receipt['owned_indices']=[0]
            (d/'placement-receipt.json').write_text(json.dumps(receipt))
            result=json.loads((d/'result.json').read_text())
            result['captions']=[dict(start=2,end=2.4,text='第一段'),dict(start=2.4,end=3,text='第二段')]
            (d/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'增删'):sync(d,r)
            t.DeleteClips.assert_not_called()
            result['resegment']=True
            (d/'result.json').write_text(json.dumps(result))
            parts=[]
            for n,row in enumerate(result['captions']):
                item=MagicMock();item.GetUniqueId.return_value='split'+str(n);item.GetName.return_value=row['text']
                item.GetStart.return_value=90001+round(row['start']*25);item.GetEnd.return_value=90001+round(row['end']*25)
                parts.append(item)
            p.GetMediaPool.return_value.AppendToTimeline.side_effect=lambda _:tracks[2].extend(parts+[items[1]])
            with patch('vincisub.editing.import_media',return_value=[object()]):self.assertEqual(sync(d,r),2)
            self.assertEqual(tracks[2],parts+[items[1]])
            new=json.loads((d/'placement-receipt.json').read_text())
            self.assertEqual(new['owned_indices'],[0,1])
