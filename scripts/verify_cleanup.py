"""Verify cleanup and save/reload in an isolated Resolve project."""
import json
import tempfile
import time
import uuid
from pathlib import Path
from vincisub.resolve import connect, import_media
from vincisub.cleanup import clean
from vincisub.storage import write_json


def main():
    resolve,original=connect();manager=resolve.GetProjectManager()
    original_name=original.GetName();name='VinciSub_Cleanup_'+uuid.uuid4().hex[:8]
    assert manager.SaveProject()
    project=manager.CreateProject(name)
    assert project
    try:
        pool=project.GetMediaPool();timeline=pool.CreateEmptyTimeline('Cleanup test')
        timeline.AddTrack('subtitle')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'current';old=root/'old';failed=root/'failed'
            for directory in (job,old,failed):
                write_json(directory/'resolve.json',dict(project_id=project.GetUniqueId()))
                write_json(directory/'placement-receipt.json',{})
                write_json(directory/'placement.json',dict(state='error' if directory==failed else 'done'))
            text='1\n00:00:01,000 --> 00:00:02,000\n清理后保留的字幕\n'
            def media(directory,name):
                path=directory/name;path.write_text(text,encoding='utf-8-sig');return import_media(pool,path)[0]
            current=media(job,'placement-'+uuid.uuid4().hex+'.srt')
            stale=media(old,'edit-'+uuid.uuid4().hex+'.srt')
            backup=media(failed,'edit-'+uuid.uuid4().hex+'.srt')
            user=media(job,'user.srt')
            remove_ids={current.GetUniqueId(),stale.GetUniqueId()}
            keep_ids={backup.GetUniqueId(),user.GetUniqueId()}
            pool.AppendToTimeline([current]);time.sleep(.5)
            def snap():
                return [(i.GetUniqueId(),i.GetName(),i.GetStart(),i.GetEnd()) for i in timeline.GetItemListInTrack('subtitle',1)]
            before=snap();assert before
            report=clean(job,resolve);assert report['removed']==2,report
            ids={i.GetUniqueId() for i in pool.GetRootFolder().GetClipList()}
            assert not ids & remove_ids and keep_ids <= ids
            assert snap()==before
            assert len(list(root.rglob('*.srt')))==4
            assert manager.SaveProject();assert manager.CloseProject(project)
            project=manager.LoadProject(name);timeline=project.GetCurrentTimeline()
            assert snap()==before
            print('Cleanup PASS: current + historical intermediates removed; failed/user media and disk files preserved; subtitles survive save/reload.')
    finally:
        manager.CloseProject(project);assert manager.LoadProject(original_name);assert manager.DeleteProject(name)


if __name__=='__main__':main()
