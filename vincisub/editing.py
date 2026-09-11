"""Synchronize edited rows by refreshing the verified task subtitle track."""
import json
import time
import uuid
from pathlib import Path

from .placement import fingerprint, frame_rows
from .resolve import connect, import_media
from .storage import write_json
from .subtitles import Caption, to_srt


def sync(directory, resolve=None):
    directory = Path(directory)
    result = json.loads((directory/'result.json').read_text(encoding='utf-8'))
    metadata = json.loads((directory/'resolve.json').read_text(encoding='utf-8'))
    receipt_path = directory/'placement-receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if resolve is None:
        resolve, _ = connect()
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    def identity():
        p = manager.GetCurrentProject()
        return p and p.GetUniqueId() == metadata['project_id'] and p.GetCurrentTimeline() and p.GetCurrentTimeline().GetUniqueId() == metadata['timeline_id']
    if not identity():
        raise ValueError('请切回生成字幕时的原始项目和时间线。')
    if list(resolve.GetVersion()[:2]) != [21,1]:
        raise ValueError('字幕同步目前仅验证 Resolve 21.1。')
    track = receipt['track']
    def items():
        return sorted(timeline.GetItemListInTrack('subtitle',track) or [], key=lambda i:i.GetStart())
    def records(clips):
        return [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in clips]
    old = [tuple(v) for v in receipt['items']]
    original = items()
    if records(original) != old:
        raise ValueError('时间线字幕已在外部修改，已停止同步以免覆盖；请在达芬奇中继续校对。')
    fps, rows = frame_rows(result,timeline)
    target = [(r['start'],r['end'],r['text']) for r in rows]
    if len(target) != len(old):
        raise ValueError('当前只支持修改已有字幕，不能增删行。')
    changed = [n for n, (a,b) in enumerate(zip(old,target)) if a[1:] != b]
    if not changed:
        write_json(receipt_path,dict(receipt,fingerprint=fingerprint(result)))
        return track
    # Media-list SRT import must target an empty track to retain relative timing.
    changed = list(range(len(old)))
    if timeline.GetIsTrackLocked('subtitle',track):
        raise ValueError('本次字幕轨已锁定，请先解锁再保存。')
    def check():
        if not identity():
            raise RuntimeError('同步期间切换了项目或时间线，已停止。')
        if (directory/'placement-cancel').exists():
            raise RuntimeError('字幕同步已取消。')
    def media_for(values):
        path = directory/f'edit-{uuid.uuid4().hex}.srt'
        start = timeline.GetStartFrame()
        path.write_text(to_srt([Caption((a-start)/fps,(b-start)/fps,text) for a,b,text in values]),encoding='utf-8-sig')
        media = import_media(project.GetMediaPool(),path)
        if not media or len(media) != 1:
            raise RuntimeError('无法准备字幕更新素材。')
        return media
    check()
    new_media = media_for([target[n] for n in changed])
    backup_media = media_for([old[n][1:] for n in changed])
    write_json(directory/'edit-backup.json',dict(receipt=receipt,requested=result))
    enabled = {n:timeline.GetIsTrackEnabled('subtitle',n) for n in range(1,timeline.GetTrackCount('subtitle')+1)}
    before = {i.GetUniqueId() for n in enabled for i in timeline.GetItemListInTrack('subtitle',n) or []}
    old_time = timeline.GetCurrentTimecode()
    changed_clips = [original[n] for n in changed]
    mutation = False
    def activate():
        for n in enabled:
            if not timeline.SetTrackEnable('subtitle',n,n==track):
                raise RuntimeError('无法启用目标字幕轨。')
        time.sleep(.3)
    def matches(expected):
        for _ in range(20):
            current = items()
            if [v[1:] for v in records(current)] == expected:
                return current
            time.sleep(.1)
        raise RuntimeError('同步后的字幕文字或时间验证失败。')
    try:
        activate()
        check()
        if records(items()) != old:
            raise RuntimeError('同步前字幕发生变化，已停止。')
        mutation = True
        if not timeline.DeleteClips(changed_clips,False):
            raise RuntimeError('无法替换已修改字幕。')
        project.GetMediaPool().AppendToTimeline(new_media)
        check()
        actual = matches(target)
        # No extra clips may be written into any other subtitle track.
        if any(i.GetUniqueId() not in before for n in enabled if n != track
               for i in timeline.GetItemListInTrack('subtitle',n) or []):
            raise RuntimeError('字幕写入了错误轨道。')
        write_json(receipt_path,dict(fingerprint=fingerprint(result),track=track,items=records(actual)))
        return track
    except Exception as error:
        if mutation and identity():
            try:
                added = [i for n in enabled for i in timeline.GetItemListInTrack('subtitle',n) or [] if i.GetUniqueId() not in before]
                if added and not timeline.DeleteClips(added,False):
                    raise RuntimeError('无法移除未完成的新字幕')
                remaining = items()
                if records(remaining) != old:
                    if any(i.GetUniqueId() not in before for i in remaining):
                        raise RuntimeError('恢复时发现未知字幕')
                    if remaining and not timeline.DeleteClips(remaining,False):
                        raise RuntimeError('无法准备原字幕恢复')
                    activate()
                    project.GetMediaPool().AppendToTimeline(backup_media)
                restored = matches([v[1:] for v in old])
                write_json(receipt_path,dict(receipt,items=records(restored)))
            except Exception as rollback_error:
                raise RuntimeError('同步失败且恢复未完成，请检查字幕轨及 edit-backup.json。') from rollback_error
        raise error
    finally:
        if identity():
            for n,value in enabled.items():
                timeline.SetTrackEnable('subtitle',n,value)
            timeline.SetCurrentTimecode(old_time)
