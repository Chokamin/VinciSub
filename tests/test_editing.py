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
