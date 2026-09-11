"""Native secondary settings for a reference spoken script."""
from . import reference


class ReferenceWindow:
    def __init__(self,ui,dispatcher,parent,data):
        self.parent=parent;self.data=data;self.id='com.vincisub.native.reference'
        self.window=dispatcher.AddWindow(dict(ID=self.id,WindowTitle='奇奇字幕 · 参考脚本',Geometry=[300,180,640,400]),ui.VGroup([
            ui.CheckBox(dict(ID='UseScript',Text='生成字幕时参考脚本',Weight=0)),
            ui.Label(dict(Text='粘贴与本次音频相关的口播稿，最多 6000 字。实际口播可与脚本不同，字幕以音频为准。',WordWrap=True,Weight=0)),
            ui.TextEdit(dict(ID='Script',AcceptRichText=False,PlaceholderText='在这里粘贴参考脚本…')),
            ui.Label(dict(ID='ScriptStatus',WordWrap=True,Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.Button(dict(ID='CancelScript',Text='取消')),ui.Button(dict(ID='SaveScript',Text='保存'))]),
        ]))
        self.items=self.window.GetItems()
        self.window.On.SaveScript.Clicked=self.save
        self.window.On.CancelScript.Clicked=self.dismiss
        self.window.On[self.id].Close=self.dismiss

    def open(self,event=None):
        value=reference.load(self.data)
        self.items['Script'].PlainText=value['text'];self.items['UseScript'].Checked=value['enabled']
        self.items['ScriptStatus'].Text='保存在本机。更换素材时，请更新或停用参考脚本。'
        self.parent.Enabled=False;self.window.Show();self.window.Raise()

    def dismiss(self,event=None):
        self.window.Hide();self.parent.Enabled=True

    def save(self,event=None):
        try:reference.save(self.data,self.items['Script'].PlainText,self.items['UseScript'].Checked)
        except ValueError as error:
            self.items['ScriptStatus'].Text=str(error);return
        self.dismiss()

    def close(self):
        self.window.Hide();self.window.ID=self.id+'.closed.'+str(id(self.window))
