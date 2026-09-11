import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from vincisub.catalog import read_all, edit_job


class CatalogTests(unittest.TestCase):
    def scene(self):
        resolve=MagicMock();project=resolve.GetProjectManager.return_value.GetCurrentProject.return_value
        timeline=project.GetCurrentTimeline.return_value
        project.GetUniqueId.return_value='p';timeline.GetUniqueId.return_value='t'
        timeline.GetName.return_value='Timeline';timeline.GetTrackName.side_effect=lambda kind,n:f'Track {n}'
        timeline.GetSetting.return_value=25
        timeline.GetStartFrame.return_value=90000;timeline.GetEndFrame.return_value=90250
        timeline.GetTrackCount.return_value=2
        def clip(id,start,end,text):
            c=MagicMock();c.GetUniqueId.return_value=id;c.GetStart.return_value=start;c.GetEnd.return_value=end;c.GetName.return_value=text
            return c
        tracks={1:[clip('a',90025,90050,'第一轨')],2:[clip('b',90025,90075,'第二轨') ]}
        timeline.GetItemListInTrack.side_effect=lambda kind,n:tracks[n]
        return resolve,timeline

    def test_all_tracks_include_overlaps_and_ignore_marks(self):
        r,t=self.scene();catalog=read_all(r)
        self.assertEqual([(c['track'],c['start'],c['end']) for c in catalog['rows']],[(1,1,2),(2,1,3)])
        t.GetMarkInOut.assert_not_called();t.GetIsTrackEnabled.assert_not_called();t.DeleteClips.assert_not_called()

    def test_edit_maps_to_original_track_and_keeps_snapshot(self):
        r,t=self.scene();catalog=read_all(r)
        with tempfile.TemporaryDirectory() as folder:
            d=edit_job(catalog,1,dict(start=1,end=3,text='校对'),folder)
            result=json.loads((d/'result.json').read_text(encoding='utf-8'))
            receipt=json.loads((d/'placement-receipt.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['track'],2)
            self.assertEqual(receipt['items'][0][3],'第二轨')
            self.assertEqual(result['captions'][0]['text'],'校对')
            self.assertEqual(catalog['rows'][1]['text'],'第二轨')

    def test_empty_timeline_and_missing_timeline(self):
        r,t=self.scene();t.GetTrackCount.return_value=0
        self.assertEqual(read_all(r)['rows'],[])
        r.GetProjectManager.return_value.GetCurrentProject.return_value.GetCurrentTimeline.return_value=None
        with self.assertRaisesRegex(ValueError,'打开时间线'):read_all(r)
