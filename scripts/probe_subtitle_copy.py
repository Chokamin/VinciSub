"""Experimental subtitle positioning probe in a disposable project.

This validates DRT-copy positioning only; it is not a production import path.
Never add source frame bounds to SRT AppendToTimeline (known Resolve crash).
The original project is saved, restored, and never used for test inserts.

Run from the project root: .venv/bin/python -m scripts.probe_subtitle_copy SAMPLE.mp4
"""

import argparse
import json
import uuid
from pathlib import Path

from vincisub.resolve import connect, import_media


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    if not args.sample.is_file():
        parser.error("样本文件不存在")
    resolve, original = connect()
    manager = resolve.GetProjectManager()
    original_name = original.GetName()
    original_page = resolve.GetCurrentPage()
    if original.IsRenderingInProgress():
        raise RuntimeError("请在渲染结束后验证。")
    if not manager.SaveProject():
        raise RuntimeError("无法保存当前项目，已停止验证。")
    name = "VinciSub_MVP_TEST_" + uuid.uuid4().hex[:8]
    temporary = manager.CreateProject(name)
    if not temporary:
        raise RuntimeError("无法创建独立验证项目。")
    output = Path("/private/tmp") / name
    try:
        output.mkdir(parents=True)
        pool = temporary.GetMediaPool()
        clips = import_media(pool, args.sample.resolve())
        if not clips:
            raise RuntimeError("测试音频无法导入。")
        timeline = pool.CreateTimelineFromClips("VinciSub sample", clips)
        if not timeline:
            raise RuntimeError("无法创建测试时间线。")
        temporary.SetCurrentTimeline(timeline)
        manager.SaveProject()
        srt = output / "verification.srt"
        srt.write_text("1\n00:00:00,100 --> 00:00:01,000\n字幕导入验证\n", encoding="utf-8-sig")
        timeline.SetStartTimecode("01:00:00:00")
        imported = import_media(pool, srt)
        timeline.AddTrack('subtitle')
        timeline.SetCurrentTimecode('01:00:00:00')
        print('append', pool.AppendToTimeline([dict(mediaPoolItem=imported[0], recordFrame=0, trackIndex=1)]), flush=True)
        print('subtitles', [(i.GetName(),i.GetStart(),i.GetEnd()) for i in timeline.GetItemListInTrack('subtitle',1)], flush=True)
        archive = output / 'source.drt'
        assert timeline.Export(str(archive), resolve.EXPORT_DRT)
        import zipfile
        import xml.etree.ElementTree as ET
        edited = output / 'positioned.drt'
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(edited, 'w') as dst:
            count = 0
            for name_in_zip in src.namelist():
                data = src.read(name_in_zip)
                if name_in_zip.startswith('SeqContainer/'):
                    root = ET.fromstring(data)
                    for caption in root.findall('./SubtitleTrackVec/Element/Sm2TiTrack/Items/Element/Sm2TiGenerator'):
                        caption.find('Start').text = '90003'
                        count += 1
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                dst.writestr(name_in_zip, data)
        assert count == 1
        copied = pool.ImportTimelineFromFile(str(edited), {'timelineName':'Positioned subtitle copy'})
        assert copied, 'Cannot import copy'
        captions = copied.GetItemListInTrack('subtitle', 1)
        print('copy', [(i.GetName(),i.GetStart(),i.GetEnd()) for i in captions], flush=True)
        assert len(captions) == 1 and captions[0].GetStart() == 90003 and captions[0].GetEnd() == 90025
        assert timeline.GetItemListInTrack('subtitle',1)[0].GetStart() == 90220
        print('original unchanged; copy video/audio', copied.GetTrackCount('video'), copied.GetTrackCount('audio'), flush=True)
        print(json.dumps(dict(positioned_copy=True, temporary_project=True)))
    finally:
        manager.CloseProject(temporary)
        if not manager.LoadProject(original_name):
            raise RuntimeError(f"请手动重新打开原项目：{original_name}")
        if original_page:
            resolve.OpenPage(original_page)
        if name in manager.GetProjectListInCurrentFolder() and not manager.DeleteProject(name):
            raise RuntimeError(f"验证完成，但测试项目需手动删除：{name}")


if __name__ == "__main__":
    main()
