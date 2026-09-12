"""Native, previewable subtitle optimization options."""
from .optimize import optimize
import json
import os
import subprocess
import uuid
from .storage import ROOT,write_json
from . import reference, vocabulary


class OptimizeWindow:
    def __init__(self,ui,dispatcher,parent,sources,apply,prepare_alignment,jobs):
        self.parent=parent;self.sources=sources;self.apply=apply
        self.prepare_alignment=prepare_alignment;self.jobs=jobs;self.process=None;self.aligned=None;self.alignment_key=None
        self.id='com.vincisub.native.optimize'
        self.window=dispatcher.AddWindow(dict(ID=self.id,WindowTitle='奇奇字幕 · 一键优化',Geometry=[300,160,680,560]),ui.VGroup([
            ui.ComboBox(dict(ID='OptimizeTrack',Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.CheckBox(dict(ID='Resegment',Text='重新断句（优先标点，结合音频定位）')),ui.Label(dict(Text='每条字数',Weight=0)),ui.SpinBox(dict(ID='SegmentChars',Minimum=6,Maximum=60,Value=20,Weight=0))]),
            ui.CheckBox(dict(ID='TrimEnding',Text='去掉句尾逗号、句号（保留句中标点及引号）',Checked=True,Weight=0)),
            ui.CheckBox(dict(ID='StripPunctuation',Text='去掉全部标点（优先于上一项）',Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.CheckBox(dict(ID='FillGaps',Text='填补短间隙')),ui.Label(dict(Text='最多（秒）',Weight=0)),ui.DoubleSpinBox(dict(ID='MaxGap',Minimum=0,Maximum=10,Decimals=2,Value=.5,Weight=0))]),
            ui.Label(dict(Text='只延长前句到下一句开始；超过阈值保留停顿，末句不延长。只处理所选范围内的相邻字幕。',WordWrap=True,Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.CheckBox(dict(ID='Realign',Text='重新对齐音频')),ui.Label(dict(Text='句尾保留（秒）',Weight=0)),ui.DoubleSpinBox(dict(ID='Tail',Minimum=0,Maximum=1,Decimals=2,Value=.15,Weight=0))]),
            ui.Label(dict(Text='使用主面板所选音轨，在原时间前后 1 秒内重新对齐。先计算预览，不可靠的条目保留时间并列出。',WordWrap=True,Weight=0)),
            ui.CheckBox(dict(ID='ScriptOptimize',Text='参考脚本优化（结合音频重新识别文字）',Weight=0)),
            ui.TextEdit(dict(ID='OptimizePreview',ReadOnly=True,AcceptRichText=False)),
            ui.Label(dict(ID='OptimizeStatus',WordWrap=True,Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.Button(dict(ID='CancelOptimize',Text='取消')),ui.Button(dict(ID='ApplyOptimize',Text='应用并同步'))]),
        ]))
        self.items=self.window.GetItems()
        for key in ['TrimEnding','StripPunctuation','FillGaps','Realign','ScriptOptimize','Resegment']:
            self.window.On[key].Clicked=self.preview
        self.window.On.SegmentChars.ValueChanged=self.preview
        self.window.On.Tail.ValueChanged=self.preview
        self.window.On.MaxGap.ValueChanged=self.preview
        self.window.On.OptimizeTrack.CurrentIndexChanged=self.preview
        self.window.On.CancelOptimize.Clicked=self.dismiss
        self.window.On.ApplyOptimize.Clicked=self.submit
        self.window.On[self.id].Close=self.dismiss
        self.options=[]

    def open(self,event=None):
        self.aligned=None;self.alignment_key=None
        self.options=self.sources()
        if not self.options:raise ValueError('请先生成字幕或读取全部字幕。')
        self.items['OptimizeTrack'].Clear()
        self.items['OptimizeTrack'].AddItems([item['label'] for item in self.options])
        self.preview();self.parent.Enabled=False;self.window.Show();self.window.Raise()

    def key(self,source):
        script=reference.load(self.jobs.data)['text'] if self.items['ScriptOptimize'].Checked else ''
        if self.items['ScriptOptimize'].Checked and not script:raise ValueError('请先在主面板「参考脚本…」中填写并保存脚本。')
        return (source['track'],self.items['Tail'].Value,bool(self.items['Realign'].Checked),bool(self.items['ScriptOptimize'].Checked),script,bool(self.items['Resegment'].Checked),self.items['SegmentChars'].Value)

    def needs_model(self):
        return self.items['Realign'].Checked or self.items['ScriptOptimize'].Checked or self.items['Resegment'].Checked

    def calculate(self):
        source=self.options[max(0,self.items['OptimizeTrack'].CurrentIndex)]
        ready=self.needs_model() and self.aligned is not None and self.alignment_key==self.key(source)
        base=self.aligned['rows'] if ready else source['rows']
        rows=optimize(base,ending=self.items['TrimEnding'].Checked,
                      all_punctuation=self.items['StripPunctuation'].Checked,
                      fill_gaps=self.items['FillGaps'].Checked,max_gap=self.items['MaxGap'].Value)
        if ready:
            for i in self.aligned['failed']:
                rows[i]['start']=base[i]['start'];rows[i]['end']=base[i]['end']
        return source,rows

    def preview(self,event=None):
        if not self.options:return
        try:
            source,rows=self.calculate()
            changes=[(a,b) for a,b in zip(source['rows'],rows) if a!=b]
            resized=len(source['rows'])!=len(rows)
            self.items['OptimizePreview'].PlainText='\n\n'.join(f"{a['text']} → {b['text']}\n时间：{a['start']:.3f}–{a['end']:.3f}s → {b['start']:.3f}–{b['end']:.3f}s" for a,b in changes[:8]) or '没有需要修改的字幕。'
            self.items['OptimizeStatus'].Text=f'原 {len(source["rows"])} 条 → 优化后 {len(rows)} 条。预览最多显示 8 条。'
            if resized:
                self.items['OptimizePreview'].PlainText='重新断句后的字幕：\n\n'+'\n\n'.join(f"{r['start']:.3f}–{r['end']:.3f}s  {r['text']}" for r in rows[:8])
            pending=self.needs_model() and (self.aligned is None or self.alignment_key!=self.key(source))
            self.items['ApplyOptimize'].Text=('计算重新断句' if self.items['Resegment'].Checked else ('计算脚本优化' if self.items['ScriptOptimize'].Checked else '计算音频对齐')) if pending else '应用并同步'
            self.items['ApplyOptimize'].Enabled=bool(changes) or resized or pending
            if pending:self.items['OptimizeStatus'].Text='先结合音频计算，再预览并应用；参考脚本可能与实际口播不同。'
            elif self.needs_model() and self.aligned['failed']:
                self.items['OptimizeStatus'].Text+=' 需校对序号：'+', '.join(str(i+1) for i in self.aligned['failed'])
        except ValueError as error:
            self.items['OptimizeStatus'].Text=str(error);self.items['ApplyOptimize'].Enabled=False

    def submit(self,event=None):
        try:
            source,rows=self.calculate()
            if self.needs_model() and (self.aligned is None or self.alignment_key!=self.key(source)):
                self.aligned=None
                plan=self.prepare_alignment(source)
                self.directory=self.jobs.data/'alignment'/uuid.uuid4().hex
                write_json(self.directory/'request.json',dict(rows=source['rows'],timeline=plan,resegment=bool(self.items['Resegment'].Checked),max_chars=self.items['SegmentChars'].Value,tail=self.items['Tail'].Value if self.items['Realign'].Checked else 0,realign=bool(self.items['Realign'].Checked),reference_script=self.key(source)[4],vocabulary=(lambda v:v['terms'] if v['enabled'] else [])(vocabulary.load(self.jobs.data))))
                write_json(self.directory/'status.json',dict(state='running',message='准备对齐音频…'))
                with (self.directory/'worker.log').open('ab') as log:
                    self.process=subprocess.Popen([str(self.jobs.python),'-m','vincisub.realign',str(self.directory)],cwd=ROOT,env=dict(os.environ,VINCISUB_DATA=str(self.jobs.data)),stdout=log,stderr=log)
                self.alignment_key=self.key(source)
                self.poll();return
            self.apply(dict(source,resegment=bool(self.items['Resegment'].Checked)),rows)
        except Exception as error:
            self.items['OptimizeStatus'].Text=str(error);return
        self.dismiss()

    def poll(self):
        if self.process is None:return
        running=self.process.poll() is None
        for key in ['OptimizeTrack','TrimEnding','StripPunctuation','FillGaps','MaxGap','Realign','Tail','ScriptOptimize','Resegment','SegmentChars','ApplyOptimize']:
            self.items[key].Enabled=not running
        status=json.loads((self.directory/'status.json').read_text(encoding='utf-8'))
        self.items['OptimizeStatus'].Text=status['message']
        if not running:
            self.process=None
            if status['state']=='done':
                self.aligned=json.loads((self.directory/'result.json').read_text(encoding='utf-8'));self.preview()
            else:self.items['OptimizeStatus'].Text='对齐未完成：'+status['message']

    def dismiss(self,event=None):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process=None
        self.window.Hide();self.parent.Enabled=True

    def close(self):
        self.dismiss()
        self.window.Hide();self.window.ID=self.id+'.closed.'+str(id(self.window))
