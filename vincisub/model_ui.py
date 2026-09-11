"""Secondary native model manager and lightweight download visualization."""
import html
import json
import os
import subprocess
from . import models
from .storage import ROOT,write_json


def progress_text(status,tick=0):
    if status.get('phase')!='download':
        return ''
    total=status.get('total',0);done=status.get('downloaded',0)
    if not total:
        return '📦 正在找搬运路线' + '·'*(tick%3+1)
    percent=max(0,min(100,int(status.get('progress',0))))
    filled=round(percent*24/100)
    bar='<font color="#79b9ff">'+'━'*filled+'</font><font color="#555b66">'+'━'*(24-filled)+'</font>'
    return f'📦 {html.escape(status.get("model", "").split("/")[-1])}'+ '·'*(tick%3+1)+f'<br>{bar}  {percent}%<br>{models.size_label(done)} / {models.size_label(total)}'


def update_download_progress(control,status,tick):
    control.Text=progress_text(status,tick)
    # UIManager's Visible assignment does not clear an explicitly Hidden widget.
    control.Hidden=not (status.get('phase')=='download' and status.get('state')=='running')


class ModelManager:
    def __init__(self,ui,dispatcher,parent,jobs,is_busy):
        self.jobs=jobs;self.parent=parent;self.is_busy=is_busy
        self.process=None;self.confirm=None;self.tick=0;self.following=False
        self.path=jobs.data/'model-download.json'
        self.id='com.vincisub.native.models'
        self.window=dispatcher.AddWindow(dict(ID=self.id,WindowTitle='奇奇字幕 · 模型管理',Geometry=[280,180,650,320]),ui.VGroup([
            ui.ComboBox(dict(ID='ManagedModel',Weight=0)),
            ui.Label(dict(ID='ModelInfo',WordWrap=True,Weight=0)),
            ui.Label(dict(Text='本地下载位置',Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.LineEdit(dict(ID='ModelPath',ReadOnly=True)),ui.Button(dict(ID='OpenModelFolder',Text='在 Finder 中打开',Weight=0))]),
            ui.Label(dict(Text='时间对齐模型由两种识别模型共用。删除后，下次使用会重新下载。',WordWrap=True,Weight=0)),
            ui.Label(dict(ID='ModelProgress',WordWrap=True)),
            ui.Label(dict(ID='ModelStatus',WordWrap=True,Weight=0)),
            ui.HGroup(dict(Weight=0),[ui.Button(dict(ID='DownloadModel',Text='下载 / 补全')),ui.Button(dict(ID='CancelDownload',Text='取消下载')),ui.Button(dict(ID='DeleteModel',Text='删除本地模型')),ui.Button(dict(ID='CloseModels',Text='关闭'))]),
        ]))
        self.items=self.window.GetItems()
        self.items['ManagedModel'].AddItems(models.LABELS)
        self.window.On.ManagedModel.CurrentIndexChanged=self.changed
        self.window.On.DownloadModel.Clicked=self.download
        self.window.On.CancelDownload.Clicked=lambda event:self.cancel()
        self.window.On.DeleteModel.Clicked=self.delete
        self.window.On.OpenModelFolder.Clicked=self.open_folder
        self.window.On.CloseModels.Clicked=self.dismiss
        self.window.On[self.id].Close=self.dismiss

    def busy(self):
        return self.process is not None and self.process.poll() is None

    def status(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding='utf-8'))
        return dict(state='idle',message='')

    def refresh(self):
        entries=models.inventory(self.jobs.data)
        self.entry=entries[max(0,self.items['ManagedModel'].CurrentIndex)]
        self.items['ModelInfo'].Text=self.entry['state']+' · 本地占用 '+models.size_label(self.entry['bytes'])
        self.items['ModelPath'].Text=self.entry['path']

    def changed(self,event=None):
        self.confirm=None;self.items['DeleteModel'].Text='删除本地模型'
        self.refresh()

    def open(self,event=None):
        self.changed();self.parent.Enabled=False
        self.window.Show();self.window.Raise()

    def dismiss(self,event=None):
        self.window.Hide();self.parent.Enabled=True
        self.confirm=None;self.items['DeleteModel'].Text='删除本地模型'

    def open_folder(self,event=None):
        try:
            folder=models.repo_path(self.entry['repo'],self.jobs.data)
            exists=folder.is_dir()
            if not exists:
                folder=models.cache_root(self.jobs.data)
                folder.mkdir(parents=True,exist_ok=True)
            subprocess.run(['/usr/bin/open',str(folder)],check=True,capture_output=True,timeout=10)
            self.items['ModelStatus'].Text='已在 Finder 中打开模型文件夹。' if exists else '模型尚未下载，已在 Finder 中打开下载目录。'
        except Exception as error:
            self.items['ModelStatus'].Text='无法打开文件夹：'+str(error)

    def download(self,event=None):
        if self.busy() or self.is_busy():return
        try:
            self.confirm=None;self.items['DeleteModel'].Text='删除本地模型'
            write_json(self.path,dict(state='running',phase='download',message='准备下载…',progress=0,total=0))
            with (self.jobs.data/'model-download.log').open('ab') as log:
                self.process=subprocess.Popen([str(self.jobs.python),'-m','vincisub.models',self.entry['repo'],str(self.path)],cwd=ROOT,stdout=log,stderr=log,env=dict(os.environ,VINCISUB_DATA=str(self.jobs.data)))
            self.poll()
        except Exception as error:
            self.items['ModelStatus'].Text=str(error)

    def delete(self,event=None):
        if self.busy() or self.is_busy():return
        if self.confirm!=self.entry['repo']:
            self.confirm=self.entry['repo']
            self.items['DeleteModel'].Text='确认删除 '+models.size_label(self.entry['bytes'])
            self.items['ModelStatus'].Text='将删除 '+self.entry['name']+' 的本地文件，再次点击确认。'
            return
        try:
            models.delete(self.entry['repo'],self.jobs.data)
            self.items['ModelStatus'].Text='已删除本地模型。'
            self.changed()
        except Exception as error:
            self.items['ModelStatus'].Text=str(error)

    def cancel(self):
        if self.jobs.busy() and self.jobs.status().get('phase')=='download':
            self.jobs.cancel()
        if self.busy():
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait()
            write_json(self.path,dict(state='cancelled',message='下载已取消，已下载部分会保留供下次继续。',progress=0))

    def poll(self):
        self.tick+=1
        active=self.busy() or self.is_busy()
        self.items['CancelDownload'].Enabled=self.busy() or (self.jobs.busy() and self.jobs.status().get('phase')=='download')
        for key in ['ManagedModel','DownloadModel','DeleteModel']:
            self.items[key].Enabled=not active
        if self.process is None and self.jobs.busy():
            status=self.jobs.status()
            self.items['ModelProgress'].Text=progress_text(status,self.tick)
            self.items['ModelStatus'].Text=status['message']
            self.following=True
        elif self.process is None and self.following:
            self.refresh();self.following=False
            self.items['ModelProgress'].Text=''
            self.items['ModelStatus'].Text=self.jobs.status()['message']
        if self.process is not None:
            status=self.status()
            if not self.busy() and status.get('state')=='running':
                status=dict(state='error',message='下载进程中断，可重试。')
                write_json(self.path,status)
            self.items['ModelProgress'].Text=progress_text(status,self.tick)
            self.items['ModelStatus'].Text=status['message']
            if not self.busy():
                self.refresh();self.process=None

    def close(self):
        self.window.Hide();self.window.ID=self.id+'.closed.'+str(id(self.window))
