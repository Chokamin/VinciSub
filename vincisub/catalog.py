"""Read all native subtitle tracks and prepare a selected track for proofreading."""
import uuid
from pathlib import Path

from .storage import write_json
from .subtitles import validate_captions
from .timeline import frame_rate
from .placement import fingerprint


def read_all(resolve):
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    if not timeline:
        raise ValueError('请先打开时间线。')
    fps = frame_rate(timeline.GetSetting('timelineFrameRate'))
    start = timeline.GetStartFrame()
    catalog = dict(project_id=project.GetUniqueId(),timeline_id=timeline.GetUniqueId(),
                   timeline=timeline.GetName(),duration=(timeline.GetEndFrame()-start)/fps,
                   tracks={},rows=[])
    for track in range(1,timeline.GetTrackCount('subtitle')+1):
        items = sorted(timeline.GetItemListInTrack('subtitle',track) or [],key=lambda i:i.GetStart())
        records = [(i.GetUniqueId(),i.GetStart(),i.GetEnd(),i.GetName()) for i in items]
        captions = [dict(start=(a-start)/fps,end=(b-start)/fps,text=text) for _,a,b,text in records]
        catalog['tracks'][track] = dict(name=timeline.GetTrackName('subtitle',track),items=records,captions=captions)
        for index,row in enumerate(captions):
            catalog['rows'].append(dict(row,track=track,row_index=index))
    catalog['rows'].sort(key=lambda r:(r['start'],r['track'],r['row_index']))
    return catalog


def edit_job(catalog, index, values, data):
    row = catalog['rows'][index]
    track = row['track']
    source = catalog['tracks'][track]
    captions = [dict(c) for c in source['captions']]
    captions[row['row_index']] = dict(values)
    validate_captions(captions)
    result = dict(captions=captions,duration=catalog['duration'],offset=0)
    directory = Path(data)/'jobs'/uuid.uuid4().hex
    write_json(directory/'result.json',result)
    write_json(directory/'resolve.json',{k:catalog[k] for k in ('project_id','timeline_id','timeline')})
    # Keep the read-time snapshot; sync must reject edits made since this scan.
    write_json(directory/'placement-receipt.json',dict(track=track,track_name=source['name'],
        items=source['items'],fingerprint=fingerprint(dict(captions=source['captions'],duration=catalog['duration'],offset=0))))
    write_json(directory/'status.json',dict(state='done',message='已读取时间线字幕，可校对。',progress=1))
    write_json(Path(data)/'native-latest.json',dict(id=directory.name))
    return directory
