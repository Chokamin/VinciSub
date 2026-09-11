"""Resolve UIManager window; no browser or HTTP service."""
import json
import os
from pathlib import Path

from .jobs import Jobs
from .resolve import import_subtitle

WINDOW_ID = "com.vincisub.native"


def launch(resolve, fusion, bmd):
    os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")
    ui = fusion.UIManager
    existing = ui.FindWindow(WINDOW_ID)
    if existing:
        existing.Show()
        existing.Raise()
        return
    jobs = Jobs()
    dispatcher = bmd.UIDispatcher(ui)
    window = dispatcher.AddWindow(
        {"ID": WINDOW_ID, "WindowTitle": "VinciSub · 中文字幕", "Geometry": [180, 140, 800, 700]},
        ui.VGroup([
            ui.Label({"Text": "VinciSub  ·  本地中文字幕", "Weight": 0, "Font": ui.Font({"PixelSize": 22, "Bold": True})}),
            ui.Button({"ID": "Refresh", "Text": "刷新目标时间线", "Weight": 0}),
            ui.Label({"ID": "Timeline", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.LineEdit({"ID": "File", "ReadOnly": True, "PlaceholderText": "选择本地音频或视频"}), ui.Button({"ID": "Browse", "Text": "选择文件"})]),
            ui.HGroup({"Weight": 0}, [ui.ComboBox({"ID": "Model"}), ui.Label({"Text": "每条字数", "Weight": 0}), ui.SpinBox({"ID": "Chars", "Minimum": 6, "Maximum": 60, "Value": 20})]),
            ui.Label({"Text": "先从时间线导出音频，再在这里选择文件。最长 30 分钟，最大 512 MB；首次运行需下载模型。", "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "Generate", "Text": "生成字幕"}), ui.Button({"ID": "Cancel", "Text": "取消任务"})]),
            ui.Label({"ID": "Status", "WordWrap": True, "MinimumSize": [0, 45], "Weight": 0}),
            ui.Tree({"ID": "Captions", "ColumnCount": 4, "RootIsDecorated": False, "AlternatingRowColors": True}),
            ui.HGroup({"Weight": 0}, [ui.Label({"Text": "开始 / 结束（秒）", "Weight": 0}), ui.DoubleSpinBox({"ID": "Start", "Decimals": 3, "Minimum": 0, "Maximum": 1800}), ui.DoubleSpinBox({"ID": "End", "Decimals": 3, "Minimum": 0, "Maximum": 1800}), ui.Button({"ID": "Apply", "Text": "保存当前条"})]),
            ui.LineEdit({"ID": "Text", "PlaceholderText": "选择一条字幕后编辑文字", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Label({"Text": "整体偏移（秒）", "Weight": 0}), ui.DoubleSpinBox({"ID": "Offset", "Decimals": 3, "Minimum": -86400, "Maximum": 86400, "Value": 0}), ui.Button({"ID": "Export", "Text": "保存 SRT"}), ui.Button({"ID": "Import", "Text": "导入达芬奇"})]),
            ui.Label({"Text": "导入后将媒体池中的 SRT 拖到字幕轨道起点。时间以所选音频的起点为零。", "Weight": 0, "WordWrap": True}),
        ]))
    items = window.GetItems()
    items["Model"].AddItems(["Qwen3-ASR 0.6B · 轻量", "Qwen3-ASR 1.7B · 标准"])
    tree = items["Captions"]
    header = tree.NewItem()
    for i, label in enumerate(["序号", "开始", "结束", "字幕"]):
        header.Text[i] = label
    tree.SetHeaderItem(header)
    for i, width in enumerate([50, 85, 85, 500]):
        tree.ColumnWidth[i] = width
    state = {"rows": [], "selected": None, "loaded": None, "status": None}

    def guard(callback):
        def wrapped(event=None):
            try:
                callback(event)
            except Exception as error:
                items["Status"].Text = str(error)
        return wrapped

    def refresh(event=None):
        project = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        items["Timeline"].Text = "当前时间线：" + (timeline.GetName() if timeline else "未打开时间线")

    def render_rows():
        state["selected"] = None
        tree.Clear()
        for index, row in enumerate(state["rows"]):
            item = tree.NewItem()
            for column, value in enumerate([str(index + 1), f'{row["start"]:.3f}', f'{row["end"]:.3f}', row["text"]]):
                item.Text[column] = value
            tree.AddTopLevelItem(item)

    def select(event=None):
        item = (event or {}).get("item") or tree.CurrentItem()
        if not item:
            return
        index = int(item.Text[0]) - 1
        state["selected"] = index
        row = state["rows"][index]
        items["Start"].Value, items["End"].Value = row["start"], row["end"]
        items["Text"].Text = row["text"]

    def save(event=None):
        if not state["rows"]:
            return
        rows = [dict(row) for row in state["rows"]]
        index = state["selected"]
        if index is not None:
            rows[index] = dict(start=items["Start"].Value, end=items["End"].Value, text=items["Text"].Text)
        jobs.save(rows, items["Offset"].Value)
        state["rows"] = rows
        render_rows()

    def browse(event=None):
        path = fusion.RequestFile("", "")
        if path:
            items["File"].Text = path

    def generate(event=None):
        save()
        jobs.start("file", items["File"].Text,
                   "qwen-0.6b" if items["Model"].CurrentIndex == 0 else "qwen-1.7b", items["Chars"].Value)
        state.update(rows=[], selected=None, loaded=None, status=None)
        render_rows()
        poll()

    def export(event=None):
        save()
        directory = fusion.RequestDir(str(Path.home()))
        if directory:
            items["Status"].Text = "已保存：" + str(jobs.export(directory))

    def import_result(event=None):
        save()
        metadata_file = jobs.directory / "resolve.json"
        metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else None
        result = import_subtitle(jobs.export(), metadata)
        items["Status"].Text = result["message"]

    def poll(event=None):
        status = jobs.status()
        signature = (status["state"], status["message"])
        if signature != state["status"]:
            items["Status"].Text = status["message"]
            state["status"] = signature
        busy = jobs.busy()
        for key in ["Generate", "Browse", "Model", "Chars"]:
            items[key].Enabled = not busy
        items["Cancel"].Enabled = busy
        done = status["state"] == "done"
        for key in ["Apply", "Export", "Import", "Text", "Start", "End", "Offset"]:
            items[key].Enabled = done
        if done and state["loaded"] != jobs.directory:
            result = jobs.result()
            state["rows"] = result["captions"]
            items["Offset"].Value = result.get("offset", 0)
            render_rows()
            state["loaded"] = jobs.directory

    def close(event=None):
        if jobs.busy():
            items["Status"].Text = "任务仍在运行，请先取消任务再关闭窗口。"
            return
        save()
        dispatcher.ExitLoop()

    for key, callback in {"Refresh": refresh, "Browse": browse, "Generate": generate, "Cancel": lambda e: jobs.cancel(), "Apply": save, "Export": export, "Import": import_result}.items():
        window.On[key].Clicked = guard(callback)
    window.On.Captions.ItemClicked = guard(select)
    window.On[WINDOW_ID].Close = guard(close)
    # Native timers deliver callbacks on the UI dispatcher thread.
    timer = ui.Timer({"ID": "VinciSubPoll", "Interval": 500, "SingleShot": False})
    dispatcher.On.Timeout = guard(poll)
    refresh()
    poll()
    window.Show()
    window.ActivateWindow()
    timer.Start()
    try:
        dispatcher.RunLoop()
    finally:
        timer.Stop()
        window.Hide()
