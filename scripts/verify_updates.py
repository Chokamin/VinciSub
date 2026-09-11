"""Exercise the native update dialog without network or timeline writes."""
import tempfile
import time
from pathlib import Path
from vincisub.resolve import connect
from vincisub.storage import ROOT


def wait_for(predicate):
    for _ in range(100):
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Native update UI timed out')


def main():
    resolve,_=connect();ui=resolve.Fusion().UIManager
    if ui.FindWindow('com.vincisub.native'):
        raise RuntimeError('Close VinciSub before verification')
    with tempfile.TemporaryDirectory() as folder:
        entry=Path(folder)/'launch.py'
        entry.write_text(f'''import sys
sys.path.insert(0,{str(ROOT)!r})
from vincisub.update_ui import UpdateWindow
ui=fusion.UIManager
d=bmd.UIDispatcher(ui)
parent=d.AddWindow(dict(ID='verify.update.parent'),ui.VGroup([]))
responses=iter([dict(message='发现新版本 v0.2.0',notes='测试更新说明',url='https://github.com/example/example/releases/tag/v0.2.0'),dict(message='当前无需更新',notes='',url='')])
w=UpdateWindow(ui,d,parent,lambda:next(responses))
import vincisub.update_ui as module
original=module.webbrowser.open
module.webbrowser.open=lambda url:True
w.window.On.CloseUpdate.Clicked=lambda event:d.ExitLoop()
timer=ui.Timer(dict(ID='verify.update.timer',Interval=100,SingleShot=False))
d.On.Timeout=lambda event:w.poll()
w.open();timer.Start()
try:d.RunLoop()
finally:
    module.webbrowser.open=original
    timer.Stop();w.close();parent.Hide()
''',encoding='utf-8')
        resolve.Fusion().RunScript(str(entry))
        wait_for(lambda:ui.FindWindow('com.vincisub.native.update'))
        window=ui.FindWindow('com.vincisub.native.update');items=window.GetItems()
        wait_for(lambda:items['OpenRelease'].Enabled)
        assert items['ReleaseNotes'].PlainText=='测试更新说明'
        ui.QueueEvent(items['OpenRelease'],'Clicked',{})
        ui.QueueEvent(items['RetryUpdate'],'Clicked',{})
        wait_for(lambda:items['UpdateStatus'].Text=='当前无需更新')
        assert not items['OpenRelease'].Enabled
        ui.QueueEvent(items['CloseUpdate'],'Clicked',{})
        wait_for(lambda:not ui.FindWindow('com.vincisub.native.update'))
    resolve.Fusion().RunScript(str(ROOT/'scripts/VinciSub.py'))
    wait_for(lambda:ui.FindWindow('com.vincisub.native'))
    parent=ui.FindWindow('com.vincisub.native')
    ui.QueueEvent(parent.GetItems()['CheckUpdate'],'Clicked',{})
    wait_for(lambda:ui.FindWindow('com.vincisub.native.update'))
    items=ui.FindWindow('com.vincisub.native.update').GetItems()
    wait_for(lambda:'尚未配置' in items['UpdateStatus'].Text)
    assert not items['OpenRelease'].Enabled
    print('Native update PASS: preview, retry, link callback, close, main button, unconfigured source. No timeline writes.')


if __name__=='__main__':main()
