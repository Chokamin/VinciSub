"""Remove only proven plugin SRT intermediates from the current media pool.

Keep on-disk SRTs and recovery records. Never infer ownership from a clip name.
"""
import json
import re
from pathlib import Path
from .storage import write_json


def eligible(path, jobs, project_id, current):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        return False
    if path.parent.parent.resolve() != jobs.resolve():
        return False
    if not re.fullmatch(r'(edit|placement)-[0-9a-f]{32}\.srt', path.name):
        return False
    try:
        metadata = json.loads((path.parent/'resolve.json').read_text(encoding='utf-8'))
        if metadata['project_id'] != project_id or not (path.parent/'placement-receipt.json').is_file():
            return False
        status = path.parent/'placement.json'
        # Current caller has just verified success; old failed/running jobs stay intact.
        if path.parent.resolve() != current.resolve():
            if not status.is_file() or json.loads(status.read_text(encoding='utf-8')).get('state') != 'done':
                return False
        return path.is_file()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def clean(directory, resolve=None):
    directory = Path(directory)
    report = dict(removed=0, skipped=0)
    try:
        if resolve is None:
            from .resolve import connect
            resolve, _ = connect()
        if list(resolve.GetVersion()[:2]) != [21, 1]:
            return report
        project = resolve.GetProjectManager().GetCurrentProject()
        metadata = json.loads((directory/'resolve.json').read_text(encoding='utf-8'))
        if project.GetUniqueId() != metadata['project_id']:
            return report
        used = set()
        for n in range(1, project.GetTimelineCount()+1):
            timeline = project.GetTimelineByIndex(n)
            for kind in ('video', 'audio', 'subtitle'):
                for track in range(1, timeline.GetTrackCount(kind)+1):
                    for item in timeline.GetItemListInTrack(kind, track) or []:
                        media = item.GetMediaPoolItem()
                        if media:
                            used.add(media.GetUniqueId())
        pool = project.GetMediaPool()
        def walk(folder):
            yield from folder.GetClipList() or []
            for child in folder.GetSubFolderList() or []:
                yield from walk(child)
        candidates = []
        for media in walk(pool.GetRootFolder()):
            path = media.GetClipProperty('File Path')
            if not isinstance(path, str) or not path or not eligible(path, directory.parent, project.GetUniqueId(), directory):
                continue
            if media.GetUniqueId() in used:
                report['skipped'] += 1
            else:
                candidates.append(media)
        if candidates:
            if resolve.GetProjectManager().GetCurrentProject().GetUniqueId() != metadata['project_id']:
                return report
            if pool.DeleteClips(candidates):
                report['removed'] = len(candidates)
            else:
                report['error'] = 'Media pool refused cleanup'
    except Exception as error:
        # Housekeeping must never roll back a successfully verified subtitle update.
        report['error'] = type(error).__name__
    try:
        write_json(directory/'cleanup.json', report)
    except OSError:
        pass
    return report
