"""Native model UI test with an isolated hardlinked cache; never delete user models."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from vincisub import models
from vincisub.resolve import connect
from vincisub.storage import DATA,ROOT


def main():
    resolve,_=connect();ui=resolve.Fusion().UIManager
    if ui.FindWindow('com.vincisub.native'):
        raise RuntimeError('Close the existing VinciSub window before verification')
    with tempfile.TemporaryDirectory(prefix='vincisub-model-ui-') as folder:
        data=Path(folder).resolve();repo=models.REPOS[0]
        source=models.repo_path(repo);dest=models.repo_path(repo,data)
        dest.parent.mkdir(parents=True)
        shutil.copytree(source,dest,symlinks=True,copy_function=os.link)
        snapshot=models.local_snapshot(repo,data)
        config=snapshot/'config.json';blob=config.resolve()
        assert blob.is_relative_to(data)
        blob.unlink();config.unlink()  # Only the test cache's hardlink; original remains intact.
        assert models.local_snapshot(repo) is not None
        entry=data/'launch.py'
        entry.write_text(f'import sys\nsys.path.insert(0,{str(ROOT)!r})\nimport vincisub.native_ui as native\nfrom vincisub.jobs import Jobs\nfrom pathlib import Path\nnative.Jobs=lambda:Jobs(data=Path({str(data)!r}))\ntry:\n    native.launch(resolve,fusion,bmd)\nfinally:\n    native.Jobs=Jobs\n',encoding='utf-8')
        window=None
        try:
            resolve.Fusion().RunScript(str(entry))
            for _ in range(100):
                window=ui.FindWindow('com.vincisub.native')
                if window:break
                time.sleep(.1)
            assert window
            main_items=window.GetItems()
            ui.QueueEvent(main_items['ModelManager'],'Clicked',{})
            time.sleep(.5)
            manager=ui.FindWindow('com.vincisub.native.models');items=manager.GetItems()
            assert '下载未完成' in items['ModelInfo'].Text
            assert items['ModelPath'].Text==str(dest)
            ui.QueueEvent(items['OpenModelFolder'],'Clicked',{});time.sleep(1)
            assert '已在 Finder 中打开模型文件夹' in items['ModelStatus'].Text
            ui.QueueEvent(items['DownloadModel'],'Clicked',{})
            status_path=data/'model-download.json';seen_running=False;seen_popup=False
            deadline=time.monotonic()+100
            while time.monotonic()<deadline:
                time.sleep(.1)
                if not status_path.exists():continue
                status=json.loads(status_path.read_text(encoding='utf-8'))
                popup=ui.FindWindow('com.vincisub.native.download')
                if popup and popup.GetItems()['Progress'].Text:
                    seen_popup=True
                if status['state']=='running':
                    seen_running=True
                if status['state'] in ('done','error'):break
            assert status['state']=='done',status
            assert seen_running
            assert seen_popup, 'Download must open its own window'
            assert status['total']>0 and status['downloaded']==status['total'],status
            time.sleep(1)
            assert '100%' in items['ModelProgress'].Text,items['ModelProgress'].Text
            assert models.local_snapshot(repo,data)
            # Delete only the isolated cache, through the actual two-click UI.
            ui.QueueEvent(items['DeleteModel'],'Clicked',{});time.sleep(.2)
            assert dest.exists()
            ui.QueueEvent(items['DeleteModel'],'Clicked',{});time.sleep(.5)
            assert not dest.exists()
            ui.QueueEvent(items['OpenModelFolder'],'Clicked',{});time.sleep(1)
            assert '尚未下载' in items['ModelStatus'].Text
            assert not dest.exists()
            assert models.local_snapshot(repo) is not None
            ui.QueueEvent(items['CloseModels'],'Clicked',{});time.sleep(.2)
            ui.QueueEvent(window,'Close',{'close':True});time.sleep(.5)
            assert not ui.FindWindow('com.vincisub.native')
            window=None
            print(json.dumps(dict(native_finder=True,download_progress=True,native_delete=True,user_models_preserved=True)))
        finally:
            if window:
                manager=ui.FindWindow('com.vincisub.native.models')
                if manager:
                    controls=manager.GetItems()
                    ui.QueueEvent(controls['CancelDownload'],'Clicked',{})
                    time.sleep(.5)
                    ui.QueueEvent(controls['CloseModels'],'Clicked',{})
                ui.QueueEvent(window,'Close',{'close':True})
                time.sleep(.5)


if __name__=='__main__':main()
