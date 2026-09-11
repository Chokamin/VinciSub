"""Write a complete SRT to the source timeline through the media-list API."""
import hashlib
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path

from .resolve import connect, import_media
from .storage import DATA, write_json


def frame_rows(result, timeline):
    fps = float(timeline.GetSetting('timelineFrameRate'))
    if fps not in (24, 25, 30, 48, 50, 60):
        raise ValueError('自动字幕定位目前支持整数帧率 24/25/30/48/50/60。')
    fps = int(fps)
    start, end = timeline.GetStartFrame(), timeline.GetEndFrame()
    offset = result.get('offset', 0)
    rows = []
    for caption in result['captions']:
        left = start + math.floor((caption['start'] + offset) * fps + .5)
        right = start + math.floor((caption['end'] + offset) * fps + .5)
        if left < start or right > end or left >= right or (rows and left < rows[-1]['end']):
            raise ValueError('字幕按帧对齐后越界、重叠或不足一帧，请先校对。')
        rows.append(dict(start=left, end=right, text=caption['text']))
    if not rows:
        raise ValueError('没有可写入的字幕。')
    return fps, rows


def fingerprint(result):
    return hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def reusable_job(directory, metadata, timeline, rows):
    """Use current contents of a known VinciSub track, including manual corrections."""
    directory = Path(directory)
    known_names = set()
    for path in directory.parent.glob('*/placement-receipt.json'):
        if path.parent == directory:
            continue
        try:
            source = json.loads((path.parent/'resolve.json').read_text(encoding='utf-8'))
            if any(source.get(k) != metadata.get(k) for k in ('project_id','timeline_id')):
                continue
            receipt = json.loads(path.read_text(encoding='utf-8'))
            known_names.add('VinciSub ' + path.parent.name[:8])
            if isinstance(receipt.get('track_name'), str):
                known_names.add(receipt['track_name'])
        except (OSError,ValueError,KeyError,TypeError):
            continue
    left = min(metadata.get('start',rows[0]['start']),rows[0]['start'])
    right = max(metadata.get('end',rows[-1]['end']),rows[-1]['end'])
    tracks = list(range(1,timeline.GetTrackCount('subtitle')+1))
    tracks.sort(key=lambda n:(not timeline.GetIsTrackEnabled('subtitle',n),n))
    decisions = []
    for track in tracks:
        name = timeline.GetTrackName('subtitle',track)
        if name not in known_names:
            continue
        if timeline.GetIsTrackLocked('subtitle',track):
            decisions.append(dict(track=track,reason='locked'))
            continue
        current = sorted(timeline.GetItemListInTrack('subtitle',track) or [],key=lambda i:i.GetStart())
        actual = [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in current]
        if any(left < v[2] and v[1] < right for v in actual):
            decisions.append(dict(track=track,reason='overlap'))
            continue
        # Freeze live contents for sync's final recheck and rollback. Do not replace
        # older job receipts: their edit ownership no longer describes this track.
        snapshot = directory/'reuse-source'
        write_json(snapshot/'placement-receipt.json',dict(
            track=track,track_name=name,items=actual,fingerprint=fingerprint(actual),owned_indices=[]))
        decisions.append(dict(track=track,reason='reuse'))
        write_json(directory/'track-selection.json',dict(start=left,end=right,tracks=decisions,selected=track))
        return snapshot
    write_json(directory/'track-selection.json',dict(start=left,end=right,tracks=decisions,selected=None))
    return None


def place(directory, resolve=None):
    directory = Path(directory)
    result = json.loads((directory/'result.json').read_text(encoding='utf-8'))
    metadata = json.loads((directory/'resolve.json').read_text(encoding='utf-8'))
    if resolve is None:
        resolve, _ = connect()
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    def identity():
        current = manager.GetCurrentProject()
        return (current and current.GetUniqueId() == metadata['project_id'] and
                current.GetCurrentTimeline() and current.GetCurrentTimeline().GetUniqueId() == metadata['timeline_id'])
    if not identity():
        raise ValueError('请切回生成字幕时的项目和原始时间线，再点击写入字幕轨。')
    if list(resolve.GetVersion()[:2]) != [21, 1]:
        raise ValueError('自动字幕落轨目前仅验证 Resolve 21.1。')
    fps, rows = frame_rows(result, timeline)
    receipt_path = directory/'placement-receipt.json'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['fingerprint'] == fingerprint(result):
            actual = timeline.GetItemListInTrack('subtitle', receipt['track']) or []
            if [(i.GetUniqueId(), i.GetStart(), i.GetEnd(), i.GetName()) for i in actual] == [tuple(x) for x in receipt['items']]:
                return receipt['track']
        raise ValueError('本任务已有字幕写入记录；请在达芬奇字幕轨内校对，避免重复写入。')
    previous = reusable_job(directory, metadata, timeline, rows)
    if previous is not None:
        from .editing import sync
        return sync(directory, resolve, append_from=previous)
    old_time = timeline.GetCurrentTimecode()
    track = timeline.GetTrackCount('subtitle') + 1
    name = 'VinciSub ' + directory.name[:8]
    ids, created = set(), False
    previous_enabled = {n: timeline.GetIsTrackEnabled('subtitle', n) for n in range(1, track)}
    misplaced = []
    def check():
        if (directory/'placement-cancel').exists():
            raise RuntimeError('字幕写入已取消。')
        if not identity():
            raise RuntimeError('写入期间切换了项目或时间线，已停止。')
    try:
        check()
        if not timeline.AddTrack('subtitle'):
            raise RuntimeError('无法创建本次字幕轨。')
        created = True
        if not timeline.SetTrackName('subtitle', track, name):
            raise RuntimeError('无法标识本次字幕轨。')
        for n in previous_enabled:
            if not timeline.SetTrackEnable('subtitle', n, False):
                raise RuntimeError('无法切换当前字幕轨。')
        if not timeline.SetTrackEnable('subtitle', track, True):
            raise RuntimeError('无法启用本次字幕轨。')
        time.sleep(.3)  # Resolve applies the active subtitle track asynchronously.
        from .subtitles import Caption, to_srt
        start = timeline.GetStartFrame()
        path = directory/f'placement-{uuid.uuid4().hex}.srt'
        path.write_text(to_srt([Caption((r['start']-start)/fps, (r['end']-start)/fps, r['text'])
                                for r in rows]), encoding='utf-8-sig')
        check()
        write_json(directory/'placement.json', dict(state='running', message=f'正在写入 {len(rows)} 条字幕…'))
        media = import_media(project.GetMediaPool(), path)
        if not media or len(media) != 1:
            raise RuntimeError('无法导入字幕素材。')
        before_ids = {i.GetUniqueId() for n in range(1, track+1)
                      for i in timeline.GetItemListInTrack('subtitle', n) or []}
        check()
        # The media-item list overload respects the SRT's timeline-relative times.
        # A clipInfo dict appends SRT at the tail; source frame bounds can crash Resolve.
        append_error = None
        try:
            project.GetMediaPool().AppendToTimeline(media)
        except Exception as error:
            append_error = error
        items = []
        for _ in range(20):
            items = timeline.GetItemListInTrack('subtitle', track) or []
            if len(items) >= len(rows):
                break
            time.sleep(.1)
        ids.update(i.GetUniqueId() for i in items if i.GetUniqueId() not in before_ids)
        misplaced = [i for n in range(1, track)
                     for i in timeline.GetItemListInTrack('subtitle', n) or []
                     if i.GetUniqueId() not in before_ids]
        if append_error:
            raise RuntimeError('字幕追加失败。') from append_error
        check()
        items = sorted(items, key=lambda i: i.GetStart())
        actual = [(i.GetUniqueId(), i.GetStart(), i.GetEnd(), i.GetName()) for i in items]
        if misplaced or [v[1:] for v in actual] != [(r['start'],r['end'],r['text']) for r in rows]:
            write_json(directory/'placement-diagnostic.json', dict(actual=actual, expected=rows,
                       misplaced=[i.GetUniqueId() for i in misplaced]))
            raise RuntimeError('字幕轨道、文字或位置回读验证失败。')
        write_json(receipt_path, dict(fingerprint=fingerprint(result), track=track, track_name=name, items=actual))
        return track
    except Exception:
        if identity():
            if misplaced and not timeline.DeleteClips(misplaced, False):
                raise RuntimeError('无法清理错轨的新字幕，请检查时间线末尾。')
            for n, enabled in previous_enabled.items():
                timeline.SetTrackEnable('subtitle', n, enabled)
        # Never delete existing/user tracks, or a track whose identity changed.
        if created and identity() and timeline.GetTrackName('subtitle',track) == name:
            remaining = timeline.GetItemListInTrack('subtitle',track) or []
            if all(i.GetUniqueId() in ids for i in remaining):
                if not timeline.DeleteTrack('subtitle',track):
                    raise RuntimeError('写入未完成，且无法清理本次字幕轨，请检查「'+name+'」。')
        raise
    finally:
        if identity():
            timeline.SetCurrentTimecode(old_time)


def main():
    directory = Path(sys.argv[1]).resolve()
    lock = DATA/'placement.lock'
    owned = False
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError('另一项字幕写入正在运行，或上次写入异常中断。请检查 placement.lock 和本次字幕轨后再重试。')
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        owned = True
        if '--update' in sys.argv[2:]:
            from .editing import sync
            track = sync(directory)
        else:
            track = place(directory)
        write_json(directory/'placement.json', dict(state='done', message=f'已写入当前时间线字幕轨 ST{track}，位置校验通过。'))
    except Exception as error:
        write_json(directory/'placement.json', dict(state='error', message=str(error)))
        raise SystemExit(1)
    finally:
        if owned:
            lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
