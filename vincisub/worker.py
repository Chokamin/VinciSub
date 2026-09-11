"""One job per process: cancellation also releases the model's memory."""

import argparse
import json
import os
import re
import shutil
import traceback
from dataclasses import asdict
from pathlib import Path

from .audio import chunks, normalize
from .storage import DATA, write_json
from .subtitles import Word, make_captions
from .vocabulary import context


MODELS = {"qwen-0.6b": "Qwen/Qwen3-ASR-0.6B", "qwen-1.7b": "Qwen/Qwen3-ASR-1.7B"}
ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B"


def with_punctuation(items, text, convert):
    """Recover punctuation from the transcript without changing aligned words."""
    cursor = 0
    for item in items:
        token = item.text.strip()
        position = text.find(token, cursor)
        suffix = ""
        if position >= 0:
            cursor = position + len(token)
            match = re.match(r"[，。！？；：、,.!?;:]+", text[cursor:])
            if match:
                suffix = match.group()
                cursor += len(suffix)
        yield Word(convert(token + suffix), float(item.start_time), float(item.end_time))


def run(job_dir):
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))

    def status(stage, message, progress=0, **extra):
        write_json(job_dir / "status.json", dict(state=stage, message=message, progress=progress, **extra))

    status("running", "正在准备音频…", 3)
    timeline = request.get("timeline")
    if timeline:
        from .timeline import decode
        samples, rate = decode(timeline, lambda n, total: status("running", f"正在读取所选音轨：{n} / {total} 个片段…", 5))
        duration = timeline["duration"]
    else:
        source = job_dir / "source"
        if request.get("input_path"):
            shutil.copyfile(request["input_path"], source)
        duration = normalize(source, job_dir / "audio.wav")
    status("running", "正在加载本地模型；首次运行会下载模型文件…", 8)
    os.environ.setdefault("HF_HOME", str(DATA / "models"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import numpy as np
    import soundfile as sf
    import torch
    from opencc import OpenCC
    from qwen_asr import Qwen3ASRModel
    from huggingface_hub import snapshot_download

    def local_model(identifier):
        try:
            return snapshot_download(identifier, local_files_only=True)
        except Exception:
            return snapshot_download(identifier, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken"])

    requested_device = os.environ.get("VINCISUB_DEVICE", "auto")
    device = requested_device if requested_device != "auto" else ("cuda:0" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    model = Qwen3ASRModel.from_pretrained(
        local_model(MODELS[request["model"]]), dtype=dtype, device_map=device,
        attn_implementation="eager", max_inference_batch_size=1, max_new_tokens=512,
        forced_aligner=local_model(ALIGNER),
        forced_aligner_kwargs=dict(dtype=dtype, device_map=device, attn_implementation="eager"),
    )
    if not timeline:
        samples, rate = sf.read(job_dir / "audio.wav", dtype="float32")
    pieces = list(chunks(samples, rate))
    converter = OpenCC("t2s")
    hints = context(request.get("vocabulary", []))
    words = []
    for index, (offset, audio) in enumerate(pieces):
        status("running", f"正在识别并对齐第 {index + 1} / {len(pieces)} 段…", 12 + round(80 * index / len(pieces)), device=device)
        if float(np.max(np.abs(audio))) < 0.0001:
            continue
        results = model.transcribe(audio=(audio, rate), context=hints, language="Chinese", return_time_stamps=True)
        for result in results:
            if not result.text.strip():
                continue
            if not result.time_stamps:
                raise RuntimeError("模型未返回时间戳，无法生成可靠字幕。")
            for word in with_punctuation(result.time_stamps, result.text, converter.convert):
                words.append(Word(word.text, word.start + offset, min(word.end + offset, duration)))
    warnings = list(timeline.get('warnings', [])) if timeline else []
    if any(word.start == word.end for word in words):
        warnings.append('部分词语时间戳已合并到相邻词语，请校对这些字幕的起止时间。')
    captions = make_captions(words, max_chars=request["max_chars"])
    if not captions:
        raise ValueError("没有识别到人声。请检查音轨或换一段清晰的人声录音。")
    rows = [asdict(c) for c in captions]
    if timeline:
        for row in rows:
            row["start"] = round(row["start"] + timeline["offset"], 3)
            row["end"] = round(row["end"] + timeline["offset"], 3)
        duration = (timeline["timeline_end"] - timeline["timeline_start"]) / timeline["fps"]
    write_json(job_dir / "result.json", dict(captions=rows, duration=duration, model=request["model"], device=device, filename=request["filename"], offset=0, warnings=warnings))
    status("done", f"已生成 {len(captions)} 条字幕，可以开始校对。", 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    args = parser.parse_args()
    try:
        run(args.job)
    except Exception as error:
        traceback.print_exc()
        write_json(args.job / "status.json", dict(state="error", message=f"{type(error).__name__}: {error}", progress=0))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
