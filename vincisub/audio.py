"""Normalize arbitrary media; split near quiet boundaries for bounded inference."""

import shutil
import subprocess
import wave


MAX_SECONDS = 30 * 60


def normalize(source, destination):
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("未找到 FFmpeg。macOS 请先运行 brew install ffmpeg。")
    command = [executable, "-nostdin", "-v", "error", "-y", "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-t", str(MAX_SECONDS + 1), "-c:a", "pcm_s16le", str(destination)]
    process = subprocess.run(command, capture_output=True, timeout=300)
    if process.returncode:
        raise ValueError("无法读取音轨，请选择有效的音频或包含音轨的视频。")
    with wave.open(str(destination), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    if duration > MAX_SECONDS:
        raise ValueError("MVP 暂支持最长 30 分钟音频，请先裁剪后重试。")
    if duration < 0.1:
        raise ValueError("音频过短或为空。")
    return duration


def chunks(samples, sample_rate=16000, seconds=25):
    import numpy as np

    start = 0
    while start < len(samples):
        end = min(start + int(seconds * sample_rate), len(samples))
        if end < len(samples):
            # Prefer a low-energy 100 ms window in the last 5 seconds.
            window = int(0.1 * sample_rate)
            candidates = range(max(start + sample_rate, end - 5 * sample_rate), end - window + 1, window)
            quiet = min(candidates, key=lambda n: float(np.mean(samples[n:n + window] ** 2)))
            end = quiet + window // 2
        yield start / sample_rate, samples[start:end]
        start = end
