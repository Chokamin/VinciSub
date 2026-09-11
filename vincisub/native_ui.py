"""Resolve UIManager window; no browser or HTTP service."""
import json
import os
import subprocess
from pathlib import Path

from .jobs import Jobs
from .storage import ROOT, write_json
from .timeline import describe_timeline, snapshot

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
            ui.Button({"ID": "Refresh", "Text": "刷新时间线 / 音轨", "Weight": 0}),
            ui.Label({"ID": "Timeline", "Weight": 0}),
            ui.ComboBox({"ID": "Track", "Weight": 0}),
            ui.Label({"ID": "Range", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.ComboBox({"ID": "Model"}), ui.Label({"Text": "每条字数", "Weight": 0}), ui.SpinBox({"ID": "Chars", "Minimum": 6, "Maximum": 60, "Value": 20})]),
            ui.Label({"Text": "默认识别所有可听音轨，跟随 Solo / Mute；未设入点、出点时识别整条时间线。单次最长 30 分钟。", "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "Generate", "Text": "生成字幕"}), ui.Button({"ID": "Cancel", "Text": "取消任务"})]),
            ui.Label({"ID": "Status", "WordWrap": True, "MinimumSize": [0, 45], "Weight": 0}),
            ui.Tree({"ID": "Captions", "Events": {"ItemClicked": True, "ItemDoubleClicked": True}, "ColumnCount": 4, "RootIsDecorated": False, "AlternatingRowColors": True}),
            ui.HGroup({"Weight": 0}, [ui.Label({"Text": "开始 / 结束（秒）", "Weight": 0}), ui.DoubleSpinBox({"ID": "Start", "Decimals": 3, "Minimum": 0, "Maximum": 1800}), ui.DoubleSpinBox({"ID": "End", "Decimals": 3, "Minimum": 0, "Maximum": 1800}), ui.Button({"ID": "Apply", "Text": "保存并同步"})]),
            ui.LineEdit({"ID": "Text", "PlaceholderText": "选择一条字幕后编辑文字", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Label({"Text": "整体偏移（秒）", "Weight": 0}), ui.DoubleSpinBox({"ID": "Offset", "Decimals": 3, "Minimum": -86400, "Maximum": 86400, "Value": 0}), ui.Button({"ID": "Export", "Text": "保存 SRT"}), ui.Button({"ID": "Import", "Text": "写入字幕轨"})]),
            ui.Label({"Text": "识别完成后自动写入当前时间线的字幕轨。双击字幕后在下方修改，点击「保存并同步」刷新本次字幕轨。单条样式请在校对完成后调整。", "Weight": 0, "WordWrap": True}),
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
    state = {"rows": [], "selected": None, "loaded": None, "status": None, "track_ids": [], "timeline_id": None, "range": None, "placement": None, "auto_place": None, "placing": False}

    def guard(callback):
        def wrapped(event=None):
            try:
                callback(event)
            except Exception as error:
                items["Status"].Text = str(error)
        return wrapped

    def refresh(event=None):
        info = describe_timeline(resolve)
        current = items["Track"].CurrentIndex
        previous = state["track_ids"][current] if 0 <= current < len(state["track_ids"]) else None
        items["Track"].Clear()
        state["track_ids"] = [None] + [track["index"] for track in info["tracks"]]
        items["Track"].AddItems(["自动 · 所有可听音轨（跟随 Solo / Mute）"] + [f'A{track["index"]} · {track["name"]}' for track in info["tracks"]])
        if previous in state["track_ids"] and state["timeline_id"] == info["timeline_id"]:
            items["Track"].CurrentIndex = state["track_ids"].index(previous)
        state["timeline_id"] = info["timeline_id"]
        show_range(info)

    def show_range(info):
        items["Timeline"].Text = "当前时间线：" + info["timeline"]
        label = "入点 → 出点" if info["marked"] else "整条时间线"
        items["Range"].Text = f'{label} · {info["offset"]:.2f}s – {info["offset"]+info["duration"]:.2f}s · 共 {info["duration"]:.2f} 秒'

    def render_rows():
        state["selected"] = None
        tree.Clear()
        for index, row in enumerate(state["rows"]):
            item = tree.NewItem()
            for column, value in enumerate([str(index + 1), f'{row["start"]:.3f}', f'{row["end"]:.3f}', row["text"]]):
                item.Text[column] = value
            tree.AddTopLevelItem(item)

    def select(event=None):
        event = event or {}
        item = event.get("item")
        if item is None:
            item = event.get("Item")
        if item is None:
            item = tree.CurrentItem()
        if item is None:
            selected = tree.SelectedItems() or []
            if isinstance(selected, dict):
                selected = list(selected.values())
            item = selected[0] if selected else None
        if item is None:
            return
        index = int(item.Text[0]) - 1
        state["selected"] = index
        row = state["rows"][index]
        items["Start"].Value, items["End"].Value = row["start"], row["end"]
        items["Text"].Text = row["text"]

    def edit(event=None):
        select(event)
        items["Text"].SetFocus()

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

    def generate(event=None):
        save()
        current = items["Track"].CurrentIndex
        if not 0 <= current < len(state["track_ids"]):
            raise ValueError("请选择一个音轨。")
        info = describe_timeline(resolve)
        if info["timeline_id"] != state["timeline_id"]:
            refresh()
            raise ValueError("时间线已切换，请确认音轨后重新生成。")
        plan = snapshot(resolve, state["track_ids"][current])
        show_range(plan)
        jobs.start("timeline", model="qwen-0.6b" if items["Model"].CurrentIndex == 0 else "qwen-1.7b", max_chars=items["Chars"].Value, timeline=plan)
        state.update(rows=[], selected=None, loaded=None, status=None, auto_place=jobs.directory)
        render_rows()
        poll()

    def export(event=None):
        save()
        directory = fusion.RequestDir(str(Path.home()))
        if directory:
            items["Status"].Text = "已保存：" + str(jobs.export(directory))

    def apply(event=None):
        save()
        if jobs.directory and (jobs.directory/'placement-receipt.json').exists():
            import_result()
        else:
            items["Status"].Text = "修改已保存。"

    def import_result(event=None):
        if state['placing']:
            return
        save()
        if not jobs.directory or not (jobs.directory/'resolve.json').exists():
            raise ValueError('该任务没有来源时间线信息，请重新生成。')
        (jobs.directory/'placement-cancel').unlink(missing_ok=True)
        write_json(jobs.directory/'placement.json', dict(state='running', message='正在准备写入字幕轨…'))
        log = (jobs.directory/'placement.log').open('ab')
        try:
            command = [str(jobs.python), '-m', 'vincisub.placement', str(jobs.directory)]
            if (jobs.directory/'placement-receipt.json').exists():
                command.append('--update')
            state['placement'] = subprocess.Popen(command, cwd=str(ROOT), stdout=log, stderr=log)
        finally:
            log.close()
        state['placing'] = True
        poll()

    def cancel(event=None):
        if state['placing']:
            (jobs.directory/'placement-cancel').touch()
        else:
            jobs.cancel()

    def poll(event=None):
        if state['placing']:
            for key in ['Generate', 'Track', 'Refresh', 'Model', 'Chars', 'Apply', 'Export', 'Import', 'Text', 'Start', 'End', 'Offset']:
                items[key].Enabled = False
            items['Cancel'].Enabled = True
            path = jobs.directory/'placement.json'
            placement = json.loads(path.read_text(encoding='utf-8'))
            items['Status'].Text = placement['message']
            if state['placement'].poll() is not None:
                state['placing'] = False
                if placement['state'] == 'running':
                    items['Status'].Text = '字幕写入进程中断，请检查本次 VinciSub 字幕轨。'
            return
        status = jobs.status()
        signature = (status["state"], status["message"])
        if signature != state["status"]:
            items["Status"].Text = status["message"]
            state["status"] = signature
        busy = jobs.busy()
        for key in ["Generate", "Track", "Refresh", "Model", "Chars"]:
            items[key].Enabled = not busy
        items["Cancel"].Enabled = busy
        if not busy:
            try:
                info = describe_timeline(resolve)
                if info["timeline_id"] != state["timeline_id"]:
                    refresh()
                else:
                    show_range(info)
            except ValueError:
                items["Range"].Text = "请打开有效时间线并刷新。"
        done = status["state"] == "done"
        for key in ["Apply", "Export", "Import", "Text", "Start", "End", "Offset"]:
            placed = jobs.directory and (jobs.directory/"placement-receipt.json").exists()
            items[key].Enabled = done
        if done and state["loaded"] != jobs.directory:
            result = jobs.result()
            state["rows"] = result["captions"]
            items["Start"].Maximum = result["duration"]
            items["End"].Maximum = result["duration"]
            items["Offset"].Value = result.get("offset", 0)
            render_rows()
            state["loaded"] = jobs.directory
            if state['auto_place'] == jobs.directory:
                state['auto_place'] = None
                import_result()
            if result.get("warnings"):
                items["Status"].Text += " " + " ".join(result["warnings"])

    def close(event=None):
        if jobs.busy() or state["placing"]:
            items["Status"].Text = "任务仍在运行，请先取消任务再关闭窗口。"
            return
        save()
        dispatcher.ExitLoop()

    for key, callback in {"Refresh": refresh, "Generate": generate, "Cancel": cancel, "Apply": apply, "Export": export, "Import": import_result}.items():
        window.On[key].Clicked = guard(callback)
    window.On.Captions.ItemClicked = guard(select)
    window.On.Captions.ItemDoubleClicked = guard(edit)
    window.On[WINDOW_ID].Close = guard(close)
    # Native timers deliver callbacks on the UI dispatcher thread.
    timer = ui.Timer({"ID": "VinciSubPoll", "Interval": 500, "SingleShot": False})
    dispatcher.On.Timeout = guard(poll)
    guard(refresh)()
    poll()
    window.Show()
    window.ActivateWindow()
    timer.Start()
    try:
        dispatcher.RunLoop()
    finally:
        timer.Stop()
        window.Hide()
        window.ID = WINDOW_ID + ".closed." + str(id(window))
