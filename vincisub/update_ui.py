"""Native update dialog; networking never touches UI objects."""
from queue import Queue, Empty
from threading import Thread
import webbrowser

from . import __version__, updates


class UpdateWindow:
    def __init__(self, ui, dispatcher, parent, checker=updates.check):
        self.parent = parent
        self.checker = checker
        self.results = Queue()
        self.running = False
        self.url = ''
        self.id = 'com.vincisub.native.update'
        self.window = dispatcher.AddWindow(dict(ID=self.id, WindowTitle='奇奇字幕 · 检查更新', Geometry=[320, 220, 520, 300]), ui.VGroup([
            ui.Label(dict(Text='当前版本：' + __version__, Weight=0)),
            ui.Label(dict(ID='UpdateStatus', WordWrap=True, Weight=0)),
            ui.TextEdit(dict(ID='ReleaseNotes', ReadOnly=True, AcceptRichText=False)),
            ui.HGroup(dict(Weight=0), [ui.Button(dict(ID='RetryUpdate', Text='重新检查')), ui.Button(dict(ID='OpenRelease', Text='查看新版', Enabled=False)), ui.Button(dict(ID='CloseUpdate', Text='关闭'))]),
        ]))
        self.items = self.window.GetItems()
        self.window.On.RetryUpdate.Clicked = self.start
        self.window.On.OpenRelease.Clicked = self.open_release
        self.window.On.CloseUpdate.Clicked = self.dismiss
        self.window.On[self.id].Close = self.dismiss

    def open(self, event=None):
        self.parent.Enabled = False
        self.window.Show()
        self.window.Raise()
        self.start()

    def start(self, event=None):
        if self.running:
            return
        self.running = True
        self.url = ''
        self.items['RetryUpdate'].Enabled = False
        self.items['OpenRelease'].Enabled = False
        self.items['ReleaseNotes'].PlainText = ''
        self.items['UpdateStatus'].Text = '正在检查更新…'
        def work():
            try:
                result = self.checker()
            except Exception:
                result = dict(message='检查失败，请稍后重试。', notes='', url='')
            self.results.put(result)
        Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            result = self.results.get_nowait()
        except Empty:
            return
        self.running = False
        self.url = result['url']
        self.items['UpdateStatus'].Text = result['message']
        self.items['ReleaseNotes'].PlainText = result['notes']
        self.items['OpenRelease'].Enabled = bool(self.url)
        self.items['RetryUpdate'].Enabled = True

    def open_release(self, event=None):
        if self.url and not webbrowser.open(self.url):
            self.items['UpdateStatus'].Text = '无法打开浏览器，请访问：' + self.url

    def dismiss(self, event=None):
        self.window.Hide()
        self.parent.Enabled = True

    def close(self):
        self.window.Hide()
        self.window.ID = self.id + '.closed.' + str(id(self.window))
