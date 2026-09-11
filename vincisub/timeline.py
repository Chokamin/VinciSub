"""Read-only Resolve timeline snapshot and source-audio decoding (no render jobs)."""
import json
import math
import shutil
import subprocess
from pathlib import Path

from .audibility import audible_tracks

RATE = 16000


def frame_rate(value):
    rate = float(str(value).split()[0])
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("时间线帧率无效。")
    return rate


def selection(timeline):
    fps = frame_rate(timeline.GetSetting("timelineFrameRate"))
    start, end = float(timeline.GetStartFrame()), float(timeline.GetEndFrame())
    marks = timeline.GetMarkInOut() or {}
    # Resolve marks are offsets from the timeline start; out is inclusive.
    mark = marks.get("audio") or marks.get("video") or {}
    left = max(start, start + float(mark.get("in", 0)))
    right = min(end, start + float(mark["out"]) + 1) if "out" in mark else end
    if right <= left:
        raise ValueError("入点、出点范围为空或不在时间线内。")
    return dict(fps=fps, timeline_start=start, timeline_end=end,
                start=left, end=right, marked=bool(mark),
                offset=(left-start)/fps, duration=(right-left)/fps)


def describe_timeline(resolve):
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    if not timeline:
        raise ValueError("请先打开包含音频的时间线。")
    info = selection(timeline)
    info.update(project_id=project.GetUniqueId(), timeline_id=timeline.GetUniqueId(),
                timeline=timeline.GetName(), tracks=[dict(index=n, name=timeline.GetTrackName("audio", n))
                for n in range(1, timeline.GetTrackCount("audio") + 1)])
    return info


def source_seconds(timecode, fps):
    """Media timecode origin, including SMPTE drop-frame sources."""
    parts = str(timecode).replace(';', ':').split(':')
    if len(parts) != 4:
        raise ValueError("无法读取源素材时间码。")
    h, m, s, f = map(int, parts)
    nominal = round(fps)
    frames = (h * 3600 + m * 60 + s) * nominal + f
    if ';' in str(timecode):
        drop = round(nominal * .0666666667)
        minutes = h * 60 + m
        frames -= drop * (minutes - minutes // 10)
    return frames / fps


def snapshot(resolve, track_index=None, range_seconds=None):
    info = describe_timeline(resolve)
    if range_seconds is not None:
        left,right=map(float,range_seconds)
        if not all(math.isfinite(v) for v in (left,right)) or left<0 or right<=left:
            raise ValueError('音频对齐范围无效。')
        right=min(right,(info['timeline_end']-info['timeline_start'])/info['fps'])
        if right<=left:raise ValueError('字幕超出时间线范围。')
        info.update(start=info['timeline_start']+left*info['fps'],end=info['timeline_start']+right*info['fps'],offset=left,duration=right-left)
    selected = [track_index] if isinstance(track_index, int) else list(track_index or [])
    selected = sorted(set(selected))
    if any(index not in [track['index'] for track in info['tracks']] for index in selected):
        raise ValueError("所选音轨不存在，请刷新时间线。")
    if info['duration'] > 1800:
        raise ValueError("本次识别范围超过 30 分钟，请设置入点、出点缩小范围。")
    timeline = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
    indices = selected or audible_tracks(resolve, timeline, len(info['tracks']))
    clips, warnings = [], set()
    for selected_index in indices:
        for item in timeline.GetItemListInTrack('audio', selected_index) or []:
            start, end = float(item.GetStart(True)), float(item.GetEnd(True))
            left, right = max(start, info['start']), min(end, info['end'])
            if right <= left or not item.GetClipEnabled():
                continue
            media = item.GetMediaPoolItem()
            if not media:
                raise ValueError(f"片段「{item.GetName()}」没有可读取的源素材。")
            path = media.GetClipProperty('File Path')
            if not path or not Path(path).is_file():
                raise ValueError(f"片段「{item.GetName()}」源素材离线，或为暂不支持的嵌套/复合片段。")
            fps = frame_rate(media.GetClipProperty('FPS'))
            origin = source_seconds(media.GetClipProperty('Start TC') or '00:00:00:00', fps)
            source_start = float(item.GetSourceStartTime()) - origin
            span = float(item.GetSourceEndTime()) - float(item.GetSourceStartTime()) + 1/fps
            speed = span / ((end-start)/info['fps'])
            if source_start < -.05 or speed <= 0:
                raise ValueError(f"片段「{item.GetName()}」源时间映射无效，暂不支持倒放。")
            if abs(speed - 1) < .015:
                speed = 1.0
            else:
                warnings.add('所选范围含变速片段，字幕按首尾时间映射，请重点校对变速处。')
            mapping = json.loads(item.GetSourceAudioChannelMapping())
            tracks = list(mapping.get('track_mapping', {}).values())
            if len(tracks) != 1:
                raise ValueError(f"片段「{item.GetName()}」音频通道映射无法确定。")
            if tracks[0].get('mute'):
                continue
            channels = tracks[0].get('channel_idx', [])
            embedded = int(mapping.get('embedded_audio_channels', 0))
            # Linked audio has independent sample offsets and must not be mistaken for embedded audio.
            if any(c > embedded for c in channels):
                raise ValueError(f"片段「{item.GetName()}」使用外部同步音频，当前还不支持该映射。")
            channels = [int(c)-1 for c in channels if c > 0]
            if not channels:
                continue
            clips.append(dict(path=path, channels=channels, track_index=selected_index,
                              source_start=max(0, source_start + (left-start)/info['fps']*speed),
                              duration=(right-left)/info['fps'], speed=speed,
                              offset=(left-info['start'])/info['fps']))
    if not clips:
        raise ValueError("所选音轨在当前范围内没有可识别的音频片段。")
    info.update(track_index=track_index, track_indices=indices, clips=clips, warnings=sorted(warnings))
    return info


def tempo_filters(speed):
    filters = []
    while speed > 2:
        filters.append('atempo=2')
        speed /= 2
    while speed < .5:
        filters.append('atempo=0.5')
        speed *= 2
    return filters + [f'atempo={speed:.10f}']


def decode(snapshot, progress=None):
    """Decode selected source intervals to memory. No exported audio file is created."""
    import numpy as np
    executable = shutil.which('ffmpeg')
    if not executable:
        raise RuntimeError('未找到 FFmpeg。')
    result = np.zeros(round(snapshot['duration'] * RATE), dtype=np.float32)
    for index, clip in enumerate(snapshot['clips']):
        if progress:
            progress(index + 1, len(snapshot['clips']))
        # Flatten audio streams so physical channel indices match Resolve's mapping.
        probe = subprocess.run([str(Path(executable).with_name('ffprobe')), '-v', 'error', '-select_streams', 'a',
                                '-show_entries', 'stream=channels', '-of', 'json', clip['path']],
                               capture_output=True, timeout=30, check=True)
        streams = json.loads(probe.stdout)['streams']
        count = sum(stream['channels'] for stream in streams)
        if not clip['channels'] or max(clip['channels']) >= count:
            raise ValueError('素材音频通道与时间线映射不一致。')
        mix = '+'.join(f'{1/len(clip["channels"]):.8f}*c{n}' for n in clip['channels'])
        prefix = ''.join(f'[0:a:{n}]' for n in range(len(streams)))
        graph = prefix + (f'amerge=inputs={len(streams)},' if len(streams)>1 else '')
        graph += 'pan=mono|c0=' + mix
        graph += ',' + ','.join(tempo_filters(clip['speed']))
        process = subprocess.run([executable, '-nostdin', '-v', 'error', '-ss', str(clip['source_start']),
                                  '-t', str(clip['duration']*clip['speed']), '-i', clip['path'],
                                  '-filter_complex', graph, '-ar', str(RATE), '-ac', '1', '-f', 'f32le', 'pipe:1'],
                                 capture_output=True, timeout=300)
        if process.returncode:
            raise ValueError('无法解码音轨源素材：' + Path(clip['path']).name)
        samples = np.frombuffer(process.stdout, dtype='<f4')
        start = round(clip['offset']*RATE)
        length = min(len(samples), round(clip['duration']*RATE), len(result)-start)
        if length <= 0:
            raise ValueError('源素材范围没有可读取的音频。')
        result[start:start+length] += samples[:length]
    np.clip(result, -1, 1, out=result)
    return result, RATE
