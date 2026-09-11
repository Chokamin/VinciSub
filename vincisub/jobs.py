"""Native UI job controller. Inference stays out of Resolve's interpreter."""

import json
import os
import shutil
import signal
import subprocess
import uuid
from dataclasses import asdict
from pathlib import Path

from .storage import DATA, ROOT, write_json
from .subtitles import to_srt, validate_captions
from .worker import MODELS


class Jobs:
    def __init__(self, data=DATA, python=None):
        self.data = Path(data)
        self.jobs = self.data / "jobs"
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.python = Path(python) if python else ROOT / ".venv/bin/python"
        self.process = None
        self.directory = None
        latest = self.data / "native-latest.json"
        if latest.exists():
            identifier = json.loads(latest.read_text(encoding="utf-8")).get("id", "")
            if len(identifier) == 32 and all(c in "0123456789abcdef" for c in identifier):
                candidate = self.jobs / identifier
                if (candidate / "status.json").is_file():
                    self.directory = candidate
                    if self.status()["state"] == "running":
                        self._status("error", "上次任务已中断，请重新生成。")

    def busy(self):
        return self.process is not None and self.process.poll() is None

    def _status(self, state, message, progress=0):
        write_json(self.directory / "status.json", dict(state=state, message=message, progress=progress))

    def start(self, source="file", path=None, model="qwen-0.6b", max_chars=20, timeline=None, vocabulary=None):
        if self.busy():
            raise ValueError("已有任务运行中，请等待完成或先取消。")
        if not self.python.is_file():
            raise RuntimeError("请先在 VinciSub 目录运行 bash scripts/setup.sh 安装本地识别环境。")
        if not shutil.which("ffmpeg"):
            raise RuntimeError("未找到 FFmpeg。请先安装：brew install ffmpeg")
        if source not in {"file", "timeline"} or model not in MODELS or not 6 <= max_chars <= 60:
            raise ValueError("无效的识别设置。")
        if source == "file":
            path = Path(path or "")
            if not path.is_file() or not 0 < path.stat().st_size <= 512 * 1024 * 1024:
                raise ValueError("请选择有效音视频文件，大小应在 0–512 MB 之间。")
        if source == "timeline" and (not timeline or not timeline.get("clips")):
            raise ValueError("没有可识别的时间线音频。")
        from .vocabulary import parse
        terms = parse("\n".join(vocabulary or []))
        self.directory = self.jobs / uuid.uuid4().hex
        self.directory.mkdir()
        request = dict(vocabulary=terms, source=source, model=model, max_chars=max_chars, filename=path.name if source == "file" else "当前时间线")
        if source == "file":
            request["input_path"] = str(path.resolve())
        if source == "timeline":
            request["timeline"] = timeline
            request["filename"] = timeline["timeline"]
            write_json(self.directory / "resolve.json", timeline)
        write_json(self.directory / "request.json", request)
        self._status("running", "正在准备音频…")
        with (self.directory / "worker.log").open("wb") as log:
            env = dict(os.environ, VINCISUB_DATA=str(self.data), PYTHONUNBUFFERED="1")
            try:
                self.process = subprocess.Popen([str(self.python), "-m", "vincisub.worker", str(self.directory)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            except OSError as error:
                self._status("error", str(error))
                raise RuntimeError("无法启动本地识别进程，请重新安装依赖。") from error
        write_json(self.data / "native-latest.json", {"id": self.directory.name})

    def status(self):
        if self.directory is None:
            return dict(state="idle", message="就绪。选择音轨后开始生成，范围自动跟随时间线入点、出点。", progress=0)
        status = json.loads((self.directory / "status.json").read_text(encoding="utf-8"))
        if status["state"] == "running" and self.process is not None and not self.busy():
            self._status("error", "识别进程意外退出，请查看任务日志或重试。")
            return self.status()
        return status

    def result(self):
        if self.status()["state"] != "done":
            raise ValueError("尚无已完成的字幕。")
        return json.loads((self.directory / "result.json").read_text(encoding="utf-8"))

    def save(self, rows, offset=0):
        result = self.result()
        captions = validate_captions(rows)
        to_srt(captions, offset)
        if captions[-1].end > result["duration"] + .001:
            raise ValueError("字幕时间不能超出音频长度。")
        result.update(captions=[asdict(c) for c in captions], offset=offset)
        write_json(self.directory / "result.json", result)

    def export(self, folder=None):
        result = self.result()
        filename = "VinciSub_" + self.directory.name[:12] + ".srt"
        destination = (Path(folder) if folder else self.directory) / filename
        content = to_srt(validate_captions(result["captions"]), float(result.get("offset", 0)))
        destination.write_text(content, encoding="utf-8-sig")
        return destination

    def cancel(self):
        if not self.busy():
            return
        os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        self._status("cancelled", "已取消，可重新生成。")
