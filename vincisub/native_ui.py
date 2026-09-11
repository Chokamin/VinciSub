"""Resolve UIManager window; no browser or HTTP service."""
import json
import os
import subprocess
from pathlib import Path

from .jobs import Jobs
from .catalog import read_all, edit_job
from . import vocabulary
from .model_ui import ModelManager, DownloadWindow
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
        {"ID": WINDOW_ID, "WindowTitle": "VinciSub · 奇奇字幕", "Geometry": [180, 140, 800, 700]},
        ui.VGroup([
            ui.Label({"Text": "VinciSub  ·  奇奇字幕", "Weight": 0, "Font": ui.Font({"PixelSize": 22, "Bold": True})}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "Refresh", "Text": "刷新时间线 / 音轨"}), ui.Button({"ID": "VocabularySettings", "Text": "词库设置…", "Weight": 0}), ui.Button({"ID": "ModelManager", "Text": "模型管理…", "Weight": 0})]),
            ui.Label({"ID": "Timeline", "Weight": 0}),
            ui.Label({"Text": "音轨（可多选，不勾选时自动识别）", "Weight": 0}),
            ui.Tree({"ID": "Track", "ColumnCount": 1, "HeaderHidden": True, "RootIsDecorated": False, "MinimumSize": [0, 75], "MaximumSize": [16777215, 110], "Weight": 0}),
            ui.Label({"ID": "Range", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.ComboBox({"ID": "Model"}), ui.Label({"Text": "每条字数", "Weight": 0}), ui.SpinBox({"ID": "Chars", "Minimum": 6, "Maximum": 60, "Value": 20})]),
            ui.Label({"Text": "未设入点、出点时识别整条时间线。单次最长 30 分钟。", "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "Generate", "Text": "生成字幕"}), ui.Button({"ID": "Cancel", "Text": "取消任务"})]),
            ui.Button({"ID": "ReadAll", "Text": "读取全部字幕", "Weight": 0}),
            ui.Label({"ID": "Status", "WordWrap": True, "MinimumSize": [0, 45], "Weight": 0}),
            ui.Tree({"ID": "Captions", "Events": {"ItemClicked": True, "ItemDoubleClicked": True}, "ColumnCount": 5, "RootIsDecorated": False, "AlternatingRowColors": True}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "Export", "Text": "保存 SRT"}), ui.Button({"ID": "Import", "Text": "写入字幕轨"})]),
            ui.Label({"Text": "识别完成后自动写入当前时间线的字幕轨。双击字幕打开编辑窗口，点击「保存并同步」刷新本次字幕轨。单条样式请在校对完成后调整。", "Weight": 0, "WordWrap": True}),
        ]))
    items = window.GetItems()
    editor_id = WINDOW_ID + '.editor'
    editor = dispatcher.AddWindow(
        {"ID": editor_id, "WindowTitle": "奇奇字幕 · 编辑字幕", "Geometry": [300, 220, 640, 220]},
        ui.VGroup([
            ui.HGroup({"Weight": 0}, [ui.Label({"Text": "开始 / 结束（秒）", "Weight": 0}), ui.DoubleSpinBox({"ID": "Start", "Decimals": 3, "Minimum": 0, "Maximum": 1800}), ui.DoubleSpinBox({"ID": "End", "Decimals": 3, "Minimum": 0, "Maximum": 1800})]),
            ui.TextEdit({"ID": "Text", "AcceptRichText": False, "PlaceholderText": "输入字幕文字", "MinimumSize": [0, 120], "Weight": 1}),
            ui.Label({"ID": "EditStatus", "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "CancelEdit", "Text": "取消"}), ui.Button({"ID": "Apply", "Text": "保存并同步"})]),
        ]))
    editor_items = editor.GetItems()
    items.update(editor_items)

    def dismiss_editor(event=None):
        editor.Hide()
        window.Enabled = True

    vocabulary_window_id = WINDOW_ID + '.vocabulary'
    vocabulary_window = dispatcher.AddWindow(
        {"ID": vocabulary_window_id, "WindowTitle": "奇奇字幕 · 词库设置", "Geometry": [300, 220, 520, 360]},
        ui.VGroup([
            ui.CheckBox({"ID": "UseVocabulary", "Text": "启用词库", "Weight": 0}),
            ui.Label({"Text": "每行一个词，或用逗号分隔。最多 100 个词，建议只添加当前素材相关的专名。", "WordWrap": True, "Weight": 0}),
            ui.TextEdit({"ID": "Vocabulary", "AcceptRichText": False, "PlaceholderText": "人名、品牌、专业词"}),
            ui.Label({"ID": "VocabularyStatus", "Text": "词库用于识别提示，仍需校对。", "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [ui.Button({"ID": "CancelVocabulary", "Text": "取消"}), ui.Button({"ID": "SaveVocabulary", "Text": "保存"})]),
        ]))
    vocabulary_items = vocabulary_window.GetItems()

    def dismiss_vocabulary(event=None):
        vocabulary_window.Hide()
        window.Enabled = True

    def open_vocabulary(event=None):
        value = vocabulary.load(jobs.data)
        vocabulary_items['Vocabulary'].PlainText = '\n'.join(value['terms'])
        vocabulary_items['UseVocabulary'].Checked = value['enabled']
        vocabulary_items['VocabularyStatus'].Text = '词库用于识别提示，仍需校对。'
        window.Enabled = False
        vocabulary_window.Show()
        vocabulary_window.Raise()

    def save_vocabulary(event=None):
        try:
            value = vocabulary.save(jobs.data,vocabulary_items['Vocabulary'].PlainText,vocabulary_items['UseVocabulary'].Checked)
        except ValueError as error:
            vocabulary_items['VocabularyStatus'].Text = str(error)
            return
        dismiss_vocabulary()
        items['Status'].Text = f"已保存 {len(value['terms'])} 个词。"

    vocabulary_window.On.SaveVocabulary.Clicked = save_vocabulary
    vocabulary_window.On.CancelVocabulary.Clicked = dismiss_vocabulary
    vocabulary_window.On[vocabulary_window_id].Close = dismiss_vocabulary
    items["Model"].AddItems(["Qwen3-ASR 0.6B · 轻量", "Qwen3-ASR 1.7B · 标准"])
    tree = items["Captions"]
    header = tree.NewItem()
    for i, label in enumerate(["序号", "开始", "结束", "字幕", "轨道"]):
        header.Text[i] = label
    tree.SetHeaderItem(header)
    for i, width in enumerate([50, 85, 85, 420, 65]):
        tree.ColumnWidth[i] = width
    state = {"catalog": None, "rows": [], "selected": None, "loaded": None, "status": None, "track_ids": [], "timeline_id": None, "range": None, "placement": None, "auto_place": None, "placing": False}

    model_manager = ModelManager(ui,dispatcher,window,jobs,lambda:jobs.busy() or state["placing"])

    def guard(callback):
        def wrapped(event=None):
            try:
                callback(event)
            except Exception as error:
                items["Status"].Text = str(error)
        return wrapped

    def selected_tracks():
        return [index for n, index in enumerate(state["track_ids"])
                if items["Track"].TopLevelItem(n).CheckState[0] == "Checked"]

    def refresh(event=None):
        info = describe_timeline(resolve)
        previous = selected_tracks() if state["timeline_id"] == info["timeline_id"] else []
        tracks = items["Track"]
        tracks.Clear()
        state["track_ids"] = [track["index"] for track in info["tracks"]]
        for track in info["tracks"]:
            item = tracks.NewItem()
            item.Text[0] = f'A{track["index"]} · {track["name"]}'
            item.Flags = {"ItemIsEnabled": True, "ItemIsSelectable": True, "ItemIsUserCheckable": True}
            item.CheckState[0] = "Checked" if track["index"] in previous else "Unchecked"
            tracks.AddTopLevelItem(item)
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
            for column, value in enumerate([str(index + 1), f'{row["start"]:.3f}', f'{row["end"]:.3f}', row["text"], f'ST{row["track"]}' if "track" in row else ""]):
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
        items["Text"].PlainText = row["text"]

    def edit(event=None):
        if jobs.busy() or model_manager.busy() or state['placing']:
            return
        select(event)
        if state['selected'] is None:
            return
        editor_items['EditStatus'].Text = ''
        window.Enabled = False
        editor.Show()
        editor.Raise()
        items['Text'].SetFocus()

    def save(event=None, edit_row=False):
        if state["catalog"] is not None:
            return
        if not state["rows"]:
            return
        rows = [dict(row) for row in state["rows"]]
        index = state["selected"]
        if edit_row and index is not None:
            rows[index] = dict(start=items["Start"].Value, end=items["End"].Value, text=items["Text"].PlainText)
        jobs.save(rows, jobs.result().get("offset", 0))
        state["rows"] = rows
        render_rows()

    def generate(event=None):
        save()
        info = describe_timeline(resolve)
        if info["timeline_id"] != state["timeline_id"]:
            refresh()
            raise ValueError("时间线已切换，请确认音轨后重新生成。")
        hints = vocabulary.load(jobs.data)
        plan = snapshot(resolve, selected_tracks())
        show_range(plan)
        jobs.start("timeline", model="qwen-0.6b" if items["Model"].CurrentIndex == 0 else "qwen-1.7b", max_chars=items["Chars"].Value, timeline=plan, vocabulary=hints["terms"] if hints["enabled"] else [])
        state.update(catalog=None, rows=[], selected=None, loaded=None, status=None, auto_place=jobs.directory)
        render_rows()
        poll()

    def export(event=None):
        save()
        directory = fusion.RequestDir(str(Path.home()))
        if directory:
            items["Status"].Text = "已保存：" + str(jobs.export(directory))

    def read_captions(event=None):
        if jobs.busy() or state['placing']:
            return
        catalog = read_all(resolve)
        save()
        state.update(catalog=catalog,rows=catalog['rows'],loaded=jobs.directory)
        items['Start'].Maximum = catalog['duration']
        items['End'].Maximum = catalog['duration']
        render_rows()
        current_status = jobs.status()
        state['status'] = (current_status['state'],current_status['message'])
        items['Status'].Text = f"已读取全部 {len(catalog['rows'])} 条字幕，来自 {len(catalog['tracks'])} 条字幕轨。"
        poll()

    def apply(event=None):
        if state['catalog'] is not None:
            if state['selected'] is None:
                raise ValueError('请先选择一条字幕。')
            jobs.directory = edit_job(state['catalog'],state['selected'],dict(
                start=items['Start'].Value,end=items['End'].Value,text=items['Text'].PlainText),jobs.data)
            state['loaded'] = jobs.directory
            import_result()
            return
        save(edit_row=True)
        if jobs.directory and (jobs.directory/'placement-receipt.json').exists():
            import_result()
        else:
            items["Status"].Text = "修改已保存。"

    def submit_editor(event=None):
        try:
            apply()
        except Exception as error:
            editor_items['EditStatus'].Text = str(error)
            return
        dismiss_editor()

    editor.On.Apply.Clicked = submit_editor
    editor.On.CancelEdit.Clicked = dismiss_editor
    editor.On[editor_id].Close = dismiss_editor

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
        if model_manager.busy():
            model_manager.cancel()
        elif state['placing']:
            (jobs.directory/'placement-cancel').touch()
        else:
            jobs.cancel()

    download_window = DownloadWindow(ui,dispatcher,model_manager.cancel)

    def poll(event=None):
        download_status = model_manager.status() if model_manager.busy() else jobs.status()
        model_manager.poll()
        download_window.update(download_status,model_manager.tick)
        if model_manager.busy():
            for key in ['Generate','VocabularySettings','ReadAll','Track','Refresh','Model','Chars','Apply','Export','Import']:
                items[key].Enabled = False
            items['Cancel'].Enabled = True
            return
        if state['placing']:
            for key in ['Generate', 'VocabularySettings', 'ReadAll', 'Track', 'Refresh', 'Model', 'Chars', 'Apply', 'Export', 'Import', 'Text', 'Start', 'End']:
                items[key].Enabled = False
            items['Cancel'].Enabled = True
            path = jobs.directory/'placement.json'
            placement = json.loads(path.read_text(encoding='utf-8'))
            items['Status'].Text = placement['message']
            if state['placement'].poll() is not None:
                state['placing'] = False
                if placement['state'] == 'done' and state['catalog'] is not None:
                    read_captions()
                if placement['state'] == 'running':
                    items['Status'].Text = '字幕写入进程中断，请检查本次 VinciSub 字幕轨。'
            return
        status = jobs.status()
        signature = (status["state"], status["message"])
        if signature != state["status"]:
            items["Status"].Text = status["message"]
            state["status"] = signature
        busy = jobs.busy()
        for key in ["Generate", "VocabularySettings", "ReadAll", "Track", "Refresh", "Model", "Chars"]:
            items[key].Enabled = not busy
        items["Cancel"].Enabled = busy
        if not busy:
            try:
                info = describe_timeline(resolve)
                if info["timeline_id"] != state["timeline_id"]:
                    refresh()
                    if state["catalog"] is not None:
                        read_captions()
                else:
                    show_range(info)
            except ValueError:
                items["Range"].Text = "请打开有效时间线并刷新。"
        if state['catalog'] is not None:
            for key in ['Apply','Text','Start','End']:
                items[key].Enabled = bool(state['rows'])
            for key in ['Export','Import']:
                items[key].Enabled = False
            return
        done = status["state"] == "done"
        for key in ["Apply", "Export", "Import", "Text", "Start", "End"]:
            placed = jobs.directory and (jobs.directory/"placement-receipt.json").exists()
            items[key].Enabled = done
        if done and state["loaded"] != jobs.directory:
            result = jobs.result()
            state["rows"] = result["captions"]
            items["Start"].Maximum = result["duration"]
            items["End"].Maximum = result["duration"]
            render_rows()
            state["loaded"] = jobs.directory
            if state['auto_place'] == jobs.directory:
                state['auto_place'] = None
                import_result()
            if result.get("warnings"):
                items["Status"].Text += " " + " ".join(result["warnings"])

    def close(event=None):
        if jobs.busy() or model_manager.busy() or state["placing"]:
            items["Status"].Text = "任务仍在运行，请先取消任务再关闭窗口。"
            return
        save()
        dispatcher.ExitLoop()

    for key, callback in {"ModelManager": model_manager.open, "VocabularySettings": open_vocabulary, "ReadAll": read_captions, "Refresh": refresh, "Generate": generate, "Cancel": cancel, "Export": export, "Import": import_result}.items():
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
        editor.Hide()
        editor.ID = editor_id + ".closed." + str(id(editor))
        download_window.close()
        model_manager.close()
        vocabulary_window.Hide()
        vocabulary_window.ID = vocabulary_window_id + ".closed." + str(id(vocabulary_window))
        window.Hide()
        window.ID = WINDOW_ID + ".closed." + str(id(window))
