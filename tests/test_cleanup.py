import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock
from vincisub.cleanup import eligible, clean


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.jobs=Path(self.temp.name);self.job=self.jobs/'job';self.job.mkdir()
        self.file=self.job/('edit-'+'a'*32+'.srt');self.file.write_text('test')
        (self.job/'resolve.json').write_text(json.dumps(dict(project_id='p')))
        (self.job/'placement-receipt.json').write_text('{}')

    def test_ownership_and_failed_history(self):
        self.assertTrue(eligible(self.file,self.jobs,'p',self.job))
        self.assertFalse(eligible(self.file,self.jobs,'other',self.job))
        self.assertFalse(eligible(self.file,self.jobs,'p',self.jobs/'new'))
        status=self.job/'placement.json'
        for state in ['error','running','done']:
            status.write_text(json.dumps(dict(state=state)))
            self.assertEqual(eligible(self.file,self.jobs,'p',self.jobs/'new'),state=='done')

    def test_names_paths_and_symlinks(self):
        ordinary=self.job/'edit-user.srt';ordinary.write_text('user')
        self.assertFalse(eligible(ordinary,self.jobs,'p',self.job))
        self.assertFalse(eligible(self.file,self.jobs/'elsewhere','p',self.job))
        self.file.unlink();self.file.symlink_to(ordinary)
        self.assertFalse(eligible(self.file,self.jobs,'p',self.job))

    def test_references_on_other_timelines_and_disk_retained(self):
        media=Mock();media.GetClipProperty.return_value=str(self.file);media.GetUniqueId.return_value='m'
        folder=Mock();folder.GetClipList.return_value=[media];folder.GetSubFolderList.return_value=[]
        pool=Mock();pool.GetRootFolder.return_value=folder;pool.DeleteClips.return_value=True
        timeline=Mock();timeline.GetTrackCount.return_value=1
        item=Mock();item.GetMediaPoolItem.return_value=media
        timeline.GetItemListInTrack.return_value=[item]
        project=Mock();project.GetUniqueId.return_value='p';project.GetTimelineCount.return_value=2
        project.GetTimelineByIndex.return_value=timeline;project.GetMediaPool.return_value=pool
        resolve=Mock();resolve.GetVersion.return_value=[21,1];resolve.GetProjectManager.return_value.GetCurrentProject.return_value=project
        self.assertEqual(clean(self.job,resolve)['skipped'],1);pool.DeleteClips.assert_not_called()
        timeline.GetItemListInTrack.return_value=[]
        self.assertEqual(clean(self.job,resolve)['removed'],1)
        self.assertTrue(self.file.exists())
        timeline.GetTrackCount.side_effect=RuntimeError('unavailable')
        pool.DeleteClips.reset_mock()
        self.assertIn('error',clean(self.job,resolve));pool.DeleteClips.assert_not_called()
