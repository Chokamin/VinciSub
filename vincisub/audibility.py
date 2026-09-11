"""Read Resolve 21.1 track Solo flags from a temporary timeline metadata snapshot.

GetIsTrackEnabled exposes Mute but not Solo. DRT flags are version-specific;
never guess all tracks when the metadata cannot be identified or validated.
"""
import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def xml(data):
    # Resolve emits C++ names such as ListMgt::LmVersion as XML element names.
    return ET.fromstring(re.sub(rb'(<\/?[\w]+)::', rb'\1__', data))


def read_flags(path, count):
    with zipfile.ZipFile(path) as archive:
        project = xml(archive.read('project.xml'))
        handles = project.findall('./TimelineHandleVec/Element')
        if len(handles) != 1:
            raise ValueError('无法确定当前时间线的音轨状态。')
        handle = handles[0].text
        sequence = None
        for name in archive.namelist():
            if name.startswith('MediaPool/') and name.endswith('.xml'):
                for timeline in xml(archive.read(name)).iter('Sm2Timeline'):
                    if timeline.get('DbId') == handle:
                        sequence = timeline.find('./Sequence/Sm2Sequence').get('DbId')
        matches = []
        for name in archive.namelist():
            if name.startswith('SeqContainer/') and name.endswith('.xml'):
                tracks = xml(archive.read(name)).findall('./AudioTrackVec/Element/Sm2TiTrack')
                if tracks and sequence and all(t.findtext('Sequence') == sequence for t in tracks):
                    matches.append(tracks)
        if len(matches) != 1 or len(matches[0]) != count:
            raise ValueError('时间线音轨状态与轨道数量不一致，请刷新后重试。')
        return [int(t.findtext('Flags')) for t in matches[0]]


def audible_tracks(resolve, timeline, count):
    if not count:
        raise ValueError('当前时间线没有音轨。')
    if list(resolve.GetVersion()[:2]) != [21, 1]:
        raise ValueError('自动读取 Solo 当前仅验证 Resolve 21.1；此版本请指定单条音轨。')
    with tempfile.TemporaryDirectory(prefix='vincisub-tracks-') as folder:
        path = Path(folder) / 'tracks.drt'
        if not timeline.Export(str(path), resolve.EXPORT_DRT):
            raise ValueError('无法读取时间线 Solo / Mute 状态，请重试或指定单条音轨。')
        flags = read_flags(path, count)
    enabled = [timeline.GetIsTrackEnabled('audio', n) for n in range(1, count + 1)]
    if any(value not in (True, False) or bool(flag & 2) == value
           for flag, value in zip(flags, enabled)):
        raise ValueError('读取期间音轨静音状态发生变化，请重新生成。')
    solo = any(flag & 32 for flag in flags)
    indices = [n for n, (flag, active) in enumerate(zip(flags, enabled), 1)
               if active and (not solo or flag & 32)]
    if not indices:
        raise ValueError('当前没有可听音轨，请检查 Solo / Mute 状态。')
    return indices
