"""Place captions in the source timeline via API plus the native Inspector bridge."""
import hashlib
import json
import math
import os
import plistlib
import platform
import tempfile
import subprocess
import sys
import time
from pathlib import Path

from .resolve import connect, import_media
from .storage import ROOT, DATA, write_json


def timecode(frame, fps):
    frame = int(frame)
    if frame < 0 or frame >= fps * 86400:
        raise ValueError('字幕位置超出有效时间码范围。')
    seconds, f = divmod(frame, fps)
    minutes, s = divmod(seconds, 60)
    h, m = divmod(minutes, 60)
    return f'{h:02}:{m:02}:{s:02}:{f:02}'


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


def bridge(request):
    if sys.platform != 'darwin':
        raise ValueError('自动落轨当前仅支持 macOS。')
    bundle = DATA / 'bin' / 'VinciSub Helper.app'
    binary = bundle / 'Contents' / 'MacOS' / 'ResolveCaptionBridge'
    source = ROOT / 'native' / 'ResolveCaptionBridge.swift'
    if not binary.is_file() or binary.stat().st_mtime < source.stat().st_mtime:
        binary.parent.mkdir(parents=True, exist_ok=True)
        info = dict(CFBundleExecutable=binary.name, CFBundleIdentifier='com.vincisub.caption-helper',
                    CFBundleName='VinciSub Helper', CFBundlePackageType='APPL', CFBundleVersion='1',
                    LSUIElement=True, NSAppleEventsUsageDescription='将识别结果定位到达芬奇原始时间线的字幕轨。')
        (bundle/'Contents'/'Info.plist').write_bytes(plistlib.dumps(info))
        build = subprocess.run(['/usr/bin/swiftc', '-target', platform.machine()+'-apple-macosx13.0', '-module-cache-path', str(DATA/'swift-cache'), str(source), '-o', str(binary)], capture_output=True, timeout=180)
        if build.returncode:
            (DATA/'helper-build.log').write_bytes(build.stderr)
            raise RuntimeError('无法构建界面助手，请检查 Xcode Command Line Tools 和 .vincisub/helper-build.log。')
        signed = subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', '--entitlements',
                                 str(ROOT/'native'/'Helper.entitlements'), str(bundle)], capture_output=True, timeout=30)
        if signed.returncode:
            binary.unlink(missing_ok=True)
            raise RuntimeError('无法签名 VinciSub 界面助手。')
    # Launch as its own app so macOS can request permissions for VinciSub Helper.
    # Resolve's hardened runtime has no Apple-event automation entitlement.
    with tempfile.TemporaryDirectory(prefix='bridge-', dir=DATA) as temp:
        request_path, response_path = Path(temp)/'request.json', Path(temp)/'response.json'
        write_json(request_path, request)
        process = subprocess.run(['/usr/bin/open', '-g', '-n', str(bundle), '--args',
                                  str(request_path), str(response_path)], capture_output=True, timeout=20)
        deadline = time.monotonic() + 60
        while not response_path.exists() and not process.returncode and time.monotonic() < deadline:
            time.sleep(.1)
        try:
            response = json.loads(response_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            raise RuntimeError('字幕界面助手未正常返回。') from error
        if process.returncode or not response.get('ok'):
            raise RuntimeError(response.get('message', '字幕界面操作失败。'))


def fingerprint(result):
    return hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def place(directory, resolve=None, control=bridge):
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
    control(dict(command='preflight'))
    old_time, old_page = timeline.GetCurrentTimecode(), resolve.GetCurrentPage()
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
        resolve.OpenPage('edit')
        control(dict(command='activate', project=project.GetName()))
        if not timeline.AddTrack('subtitle'):
            raise RuntimeError('无法创建本次字幕轨。')
        created = True
        if not timeline.SetTrackName('subtitle', track, name):
            raise RuntimeError('无法标识本次字幕轨。')
        if not timeline.SetTrackEnable('subtitle', track, True):
            raise RuntimeError('无法启用本次字幕轨。')
        time.sleep(.3)  # Resolve applies the active subtitle track asynchronously.
        from .subtitles import Caption, to_srt
        items = []
        # Append and position one caption at a time in chronological order.
        # Extending its start leftward never crosses an already placed caption.
        for number, target in enumerate(rows, 1):
            check()
            write_json(directory/'placement.json', dict(state='running', message=f'正在放入字幕轨 {number}/{len(rows)}'))
            path = directory/f'placement-{number:05}.srt'
            path.write_text(to_srt([Caption(0, (target['end']-target['start'])/fps, target['text'])]), encoding='utf-8-sig')
            media = import_media(project.GetMediaPool(), path)
            if not media:
                raise RuntimeError('无法导入字幕素材。')
            # NEVER pass source frame bounds to SRT (known Resolve crash).
            before_ids = {i.GetUniqueId() for n in range(1, track+1)
                          for i in timeline.GetItemListInTrack('subtitle', n) or []}
            project.GetMediaPool().AppendToTimeline([dict(mediaPoolItem=media[0], trackIndex=track)])
            added = []
            for _ in range(15):
                current = timeline.GetItemListInTrack('subtitle', track) or []
                added = [i for i in current if i.GetUniqueId() not in ids]
                if added:
                    break
                time.sleep(.1)
            ids.update(i.GetUniqueId() for i in added)
            misplaced = [i for n in range(1, track)
                         for i in timeline.GetItemListInTrack('subtitle', n) or []
                         if i.GetUniqueId() not in before_ids]
            if misplaced or len(added) != 1 or added[0].GetName() != target['text']:
                raise RuntimeError('字幕导入轨道、数量或文字不一致。')
            item = added[0]
            items.append(item)
            old_start, old_end = int(item.GetStart()), int(item.GetEnd())
            if old_start < timeline.GetStartFrame() + result['duration'] * fps:
                raise RuntimeError('字幕追加位置不符合预期，已停止自动选择。')
            timeline.SetCurrentTimecode(timecode(old_start, fps))
            control(dict(command='select', project=project.GetName()))
            # Resolve's selected-item query may omit subtitle generators.
            # The bridge requires a unique Inspector text AND both old timecodes
            # before changing either field; API readback then verifies the item.
            check()
            control(dict(command='edit', project=project.GetName(), text=target['text'],
                         old_start=timecode(old_start,fps), old_end=timecode(old_end,fps),
                         start=timecode(target['start'],fps), end=timecode(target['end'],fps)))
            for _ in range(10):
                if (item.GetStart(), item.GetEnd()) == (target['start'], target['end']):
                    break
                time.sleep(.1)
            if (item.GetStart(), item.GetEnd(), item.GetName()) != (target['start'], target['end'], target['text']):
                raise RuntimeError('字幕位置回读验证失败。')
        check()
        actual = [(i.GetUniqueId(), i.GetStart(), i.GetEnd(), i.GetName()) for i in items]
        if [(i.GetStart(), i.GetEnd(), i.GetName()) for i in items] != [(r['start'], r['end'], r['text']) for r in rows]:
            raise RuntimeError('整轨字幕最终验证失败。')
        write_json(receipt_path, dict(fingerprint=fingerprint(result), track=track, items=actual))
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
            resolve.OpenPage(old_page)


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
