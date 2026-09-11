"""Native, previewable subtitle optimization options."""
from .optimize import optimize


class OptimizeWindow:
    def __init__(self,ui,dispatcher,parent,sources,apply):
        self.parent=parent;self.sources=sources;self.apply=apply
        self.id='com.vincisub.native.optimize'
        self.window=dispatcher.AddWindow(dict(ID=self.id,WindowTitle='奇奇字幕 · 一键优化',Geometry=[300,160,640,420]),ui.VGroup([
            ui.ComboBox(dict(ID='OptimizeTrack',Weight=0)),
            ui.CheckBox(dict(ID='TrimEnding',Text='去掉句尾逗号、句号（保留句中标点及引号）',Checked=True,Weight=0)),
            ui.CheckBox(dict(ID='StripPunctuation',Text='去掉全部标点（优先于上一项）',Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.CheckBox(dict(ID='FillGaps',Text='填补短间隙')),ui.Label(dict(Text='最多（秒）',Weight=0)),ui.DoubleSpinBox(dict(ID='MaxGap',Minimum=0,Maximum=10,Decimals=2,Value=.5,Weight=0))]),
            ui.Label(dict(Text='只延长前句到下一句开始；超过阈值保留停顿，末句不延长。只处理所选范围内的相邻字幕。',WordWrap=True,Weight=0)),
            ui.TextEdit(dict(ID='OptimizePreview',ReadOnly=True,AcceptRichText=False)),
            ui.Label(dict(ID='OptimizeStatus',WordWrap=True,Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.Button(dict(ID='CancelOptimize',Text='取消')),ui.Button(dict(ID='ApplyOptimize',Text='应用并同步'))]),
        ]))
        self.items=self.window.GetItems()
        for key in ['TrimEnding','StripPunctuation','FillGaps']:
            self.window.On[key].Clicked=self.preview
        self.window.On.MaxGap.ValueChanged=self.preview
        self.window.On.OptimizeTrack.CurrentIndexChanged=self.preview
        self.window.On.CancelOptimize.Clicked=self.dismiss
        self.window.On.ApplyOptimize.Clicked=self.submit
        self.window.On[self.id].Close=self.dismiss
        self.options=[]

    def open(self,event=None):
        self.options=self.sources()
        if not self.options:raise ValueError('请先生成字幕或读取全部字幕。')
        self.items['OptimizeTrack'].Clear()
        self.items['OptimizeTrack'].AddItems([item['label'] for item in self.options])
        self.preview();self.parent.Enabled=False;self.window.Show();self.window.Raise()

    def calculate(self):
        source=self.options[max(0,self.items['OptimizeTrack'].CurrentIndex)]
        rows=optimize(source['rows'],ending=self.items['TrimEnding'].Checked,
                      all_punctuation=self.items['StripPunctuation'].Checked,
                      fill_gaps=self.items['FillGaps'].Checked,max_gap=self.items['MaxGap'].Value)
        return source,rows

    def preview(self,event=None):
        if not self.options:return
        try:
            source,rows=self.calculate()
            changes=[(a,b) for a,b in zip(source['rows'],rows) if a!=b]
            self.items['OptimizePreview'].PlainText='\n\n'.join(f"{a['text']} → {b['text']}\n结束：{a['end']:.3f}s → {b['end']:.3f}s" for a,b in changes[:8]) or '没有需要修改的字幕。'
            self.items['OptimizeStatus'].Text=f'共 {len(rows)} 条，将修改 {len(changes)} 条。预览最多显示 8 条。'
            self.items['ApplyOptimize'].Enabled=bool(changes)
        except ValueError as error:
            self.items['OptimizeStatus'].Text=str(error);self.items['ApplyOptimize'].Enabled=False

    def submit(self,event=None):
        try:
            source,rows=self.calculate()
            self.apply(source,rows)
        except Exception as error:
            self.items['OptimizeStatus'].Text=str(error);return
        self.dismiss()

    def dismiss(self,event=None):
        self.window.Hide();self.parent.Enabled=True

    def close(self):
        self.window.Hide();self.window.ID=self.id+'.closed.'+str(id(self.window))
