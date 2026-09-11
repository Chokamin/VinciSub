"""Real model and native preview test; no timeline writes or user setting changes."""
import json
import tempfile
import time
from pathlib import Path
from vincisub.resolve import connect
from vincisub.storage import ROOT,write_json


def main():
    resolve,_=connect();ui=resolve.Fusion().UIManager
    with tempfile.TemporaryDirectory(prefix='vincisub-script-opt-') as folder:
        root=Path(folder)
        row=dict(start=.5,end=8,text='大家好，欢迎使用中午字幕工具。今天我们测试语音识别。')
        plan=dict(offset=0,duration=8.68,fps=25,clips=[dict(path=str(ROOT/'.vincisub/verification/mandarin.mp4'),channels=[0],source_start=0,duration=8.68,speed=1,offset=0)])
        launch=root/'launch.py';result=root/'result.json'
        launch.write_text(f'''import sys
sys.path.insert(0,{str(ROOT)!r})
from pathlib import Path
from vincisub.optimize_ui import OptimizeWindow
from vincisub.jobs import Jobs
from vincisub.storage import write_json
ui=fusion.UIManager
d=bmd.UIDispatcher(ui)
parent=d.AddWindow(dict(ID='vincisub.verify.parent'),ui.VGroup([]))
def apply(source,rows):
    write_json(Path({str(result)!r}),rows)
    d.ExitLoop()
w=OptimizeWindow(ui,d,parent,lambda:[dict(label='验证样本',track=None,rows=[{row!r}])],apply,lambda source:{plan!r},Jobs())
timer=ui.Timer(dict(ID='VerifyOptimizeTimer',Interval=200,SingleShot=False))
d.On.Timeout=lambda event:w.poll()
w.open();timer.Start()
try:d.RunLoop()
finally:
    timer.Stop();w.close();parent.Hide()
''',encoding='utf-8')
        resolve.Fusion().RunScript(str(launch));time.sleep(.6)
        window=ui.FindWindow('com.vincisub.native.optimize');items=window.GetItems()
        items['TrimEnding'].Checked=False;items['ScriptOptimize'].Checked=True
        items['OptimizeScript'].PlainText='大家好，欢迎使用中文字幕工具。今天我们测试自动字幕。'
        ui.QueueEvent(items['ScriptOptimize'],'Clicked',{});time.sleep(.2)
        assert items['ApplyOptimize'].Text=='计算脚本优化'
        ui.QueueEvent(items['ApplyOptimize'],'Clicked',{})
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            time.sleep(.3)
            if items['ApplyOptimize'].Text=='应用并同步':break
        assert items['ApplyOptimize'].Text=='应用并同步',items['OptimizeStatus'].Text
        assert not result.exists()
        assert '中文字幕工具' in items['OptimizePreview'].PlainText
        ui.QueueEvent(items['ApplyOptimize'],'Clicked',{})
        for _ in range(30):
            if result.exists():break
            time.sleep(.1)
        rows=json.loads(result.read_text(encoding='utf-8'))
        assert rows[0]['start']==.5 and rows[0]['end']==8,rows
        assert '中文字幕工具' in rows[0]['text'] and '中午字幕' not in rows[0]['text'],rows
        print('Native script optimization PASS; timing preserved; no timeline writes')


if __name__=='__main__':main()
