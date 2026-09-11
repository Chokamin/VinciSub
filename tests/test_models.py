import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from vincisub import models
from vincisub.model_ui import progress_text


def fixture(data,repo=models.REPOS[0]):
    root=models.repo_path(repo,data);snap=root/'snapshots'/'revision'
    snap.mkdir(parents=True)
    (root/'refs').mkdir();(root/'refs'/'main').write_text('revision')
    for name in ['config.json','tokenizer_config.json','preprocessor_config.json','vocab.json','merges.txt','model.safetensors']:
        (snap/name).write_text('{}')
    return root,snap


class ModelTests(unittest.TestCase):
    def test_inventory_requires_complete_files_and_counts_once(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);root,snap=fixture(data)
            (snap/'link.json').symlink_to(snap/'config.json')
            entry=models.inventory(data)[0]
            self.assertEqual(entry['state'],'已下载')
            self.assertEqual(entry['bytes'],20)
            (snap/'model.safetensors').unlink()
            self.assertEqual(models.inventory(data)[0]['state'],'下载未完成')

    def test_delete_only_selected_repo_and_lock_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);root,_=fixture(data);other,_=fixture(data,models.ALIGNER)
            with models.cache_lock(data):
                with self.assertRaises(RuntimeError):models.delete(models.REPOS[0],data)
            self.assertTrue(root.exists())
            models.delete(models.REPOS[0],data)
            self.assertFalse(root.exists());self.assertTrue(other.exists())

    def test_delete_rejects_unknown_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);root=models.repo_path(models.REPOS[0],data)
            root.parent.mkdir(parents=True);outside=data/'outside';outside.mkdir();root.symlink_to(outside)
            with self.assertRaises(ValueError):models.delete(models.REPOS[0],data)
            with self.assertRaises(ValueError):models.delete('../../outside',data)
            self.assertTrue(outside.exists())

    def test_cached_ensure_has_no_network(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);_,snap=fixture(data)
            with patch('huggingface_hub.HfApi',side_effect=AssertionError('network')):
                self.assertEqual(models.ensure(models.REPOS[0],lambda _:None,data),str(snap))

    def test_download_reports_real_totals_and_rejects_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);updates=[]
            names=['config.json','tokenizer_config.json','preprocessor_config.json','vocab.json','merges.txt','model.safetensors']
            files=[SimpleNamespace(rfilename=n,size=2,lfs=None,blob_id='abc') for n in names]
            def download(repo,filename,**kw):
                p=models.repo_path(repo,data)/'snapshots'/'revision'/filename;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
            with patch('huggingface_hub.HfApi') as api,patch('huggingface_hub.hf_hub_download',side_effect=download):
                api.return_value.model_info.return_value=SimpleNamespace(sha='revision',siblings=files)
                models.ensure(models.REPOS[0],updates.append,data)
            self.assertEqual(updates[-1]['downloaded'],12)
            self.assertEqual(updates[-1]['total'],12)
            self.assertEqual(updates[-1]['progress'],100)

    def test_progress_is_not_faked_and_escapes_model_name(self):
        self.assertEqual(progress_text({'phase':'other'}),'')
        self.assertIn('25%',progress_text(dict(phase='download',total=100,downloaded=25,progress=25,model='<test>')))
        self.assertIn('&lt;test&gt;',progress_text(dict(phase='download',total=100,progress=25,model='<test>')))
        self.assertNotIn('%',progress_text(dict(phase='download',total=0)))

    def test_manager_follows_automatic_download_and_can_cancel(self):
        from unittest.mock import MagicMock
        from vincisub.model_ui import ModelManager
        manager=ModelManager.__new__(ModelManager)
        manager.tick=0;manager.process=None;manager.following=False
        manager.jobs=MagicMock();manager.jobs.busy.return_value=True
        manager.jobs.status.return_value=dict(state='running',phase='download',total=100,downloaded=25,progress=25,message='下载中')
        manager.is_busy=lambda:True
        keys=['CancelDownload','ManagedModel','DownloadModel','DeleteModel','ModelProgress','ModelStatus']
        manager.items={key:MagicMock() for key in keys}
        manager.poll()
        self.assertIn('25%',manager.items['ModelProgress'].Text)
        self.assertFalse(manager.items['DeleteModel'].Enabled)
        manager.cancel();manager.jobs.cancel.assert_called_once()

    def test_open_folder_uses_selected_model_and_missing_model_parent(self):
        from vincisub.model_ui import ModelManager
        with tempfile.TemporaryDirectory(prefix='奇奇 字幕 ') as folder:
            data=Path(folder);root,_=fixture(data)
            manager=ModelManager.__new__(ModelManager)
            manager.jobs=SimpleNamespace(data=data)
            manager.items={'ModelStatus':SimpleNamespace(Text='')}
            manager.entry={'repo':models.REPOS[0]}
            with patch('vincisub.model_ui.subprocess.run') as run:
                manager.open_folder()
                self.assertEqual(run.call_args.args[0],['/usr/bin/open',str(root)])
                self.assertIn('模型文件夹',manager.items['ModelStatus'].Text)
                manager.entry={'repo':models.ALIGNER}
                manager.open_folder()
                self.assertEqual(run.call_args.args[0],['/usr/bin/open',str(models.cache_root(data))])
                self.assertFalse(models.repo_path(models.ALIGNER,data).exists())
                self.assertIn('尚未下载',manager.items['ModelStatus'].Text)

    def test_open_folder_reports_launch_failure(self):
        from vincisub.model_ui import ModelManager
        with tempfile.TemporaryDirectory() as folder:
            manager=ModelManager.__new__(ModelManager)
            manager.jobs=SimpleNamespace(data=Path(folder))
            manager.entry={'repo':models.REPOS[0]}
            manager.items={'ModelStatus':SimpleNamespace(Text='')}
            with patch('vincisub.model_ui.subprocess.run',side_effect=OSError('Finder unavailable')):
                manager.open_folder()
            self.assertIn('无法打开文件夹',manager.items['ModelStatus'].Text)
            self.assertTrue(models.cache_root(Path(folder)).is_dir())
