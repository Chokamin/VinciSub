import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vincisub.placement import bridge, frame_rows, place, timecode


class PlacementTests(unittest.TestCase):
    def setup_scene(self, directory):
        r, p, t = MagicMock(), MagicMock(), MagicMock()
        r.GetProjectManager.return_value.GetCurrentProject.return_value = p
        p.GetCurrentTimeline.return_value = t
        p.GetUniqueId.return_value, t.GetUniqueId.return_value = 'p', 't'
        r.GetVersion.return_value = [21,1]
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 90000, 90250
        t.GetTrackCount.return_value = 1
        t.GetTrackName.return_value = 'VinciSub ' + directory.name[:8]
        result = dict(duration=10, captions=[dict(start=2,end=3,text='甲'),dict(start=5,end=6,text='乙')])
        (directory/'result.json').write_text(json.dumps(result), encoding='utf-8')
        (directory/'resolve.json').write_text(json.dumps(dict(project_id='p',timeline_id='t')), encoding='utf-8')
        items = []
        for i, row in enumerate(result['captions']):
            item = MagicMock()
            item.GetUniqueId.return_value = str(i)
            item.GetName.return_value = row['text']
            item.GetStart.return_value, item.GetEnd.return_value = 90300 + 100*i, 90325 + 100*i
            items.append(item)
        count = [0]
        def append(_):
            count[0] += 1
            return [items[count[0]-1]]
        p.GetMediaPool.return_value.AppendToTimeline.side_effect = append
        t.GetItemListInTrack.side_effect = lambda kind, track: items[:count[0]] if track == 2 else []
        t.test_items = items
        current = [0]
        def control(request):
            if request['command'] == 'select':
                t.GetSelectedClips.return_value = [items[current[0]]]
            if request['command'] == 'edit':
                row = result['captions'][current[0]]
                items[current[0]].GetStart.return_value = 90000 + row['start']*25
                items[current[0]].GetEnd.return_value = 90000 + row['end']*25
                current[0] += 1
        return r, p, t, result, control

    def test_frame_quantization_and_nonzero_start(self):
        t = MagicMock()
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 90000,90250
        fps, rows = frame_rows(dict(captions=[dict(start=2.04,end=3.04,text='你好')]), t)
        self.assertEqual((fps,rows[0]['start'],rows[0]['end']), (25,90051,90076))
        self.assertEqual(timecode(90051,25),'01:00:02:01')

    def test_rejects_collapsed_caption_before_mutation(self):
        t = MagicMock()
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value, t.GetEndFrame.return_value = 0,250
        with self.assertRaises(ValueError):
            frame_rows(dict(captions=[dict(start=2,end=2.001,text='甲')]),t)
        t.AddTrack.assert_not_called()

    def test_wrong_timeline_and_permissions_fail_before_adding(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,control = self.setup_scene(d)
            p.GetUniqueId.return_value = 'wrong'
            with self.assertRaises(ValueError): place(d,r,control)
            t.AddTrack.assert_not_called()
            p.GetUniqueId.return_value = 'p'
            with self.assertRaisesRegex(RuntimeError,'permission'):
                place(d,r,lambda request: (_ for _ in ()).throw(RuntimeError('permission')))
            t.AddTrack.assert_not_called()

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_verified_chronological_placement_and_duplicate_prevention(self, imported):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,control = self.setup_scene(d)
            self.assertEqual(place(d,r,control),2)
            args = p.GetMediaPool.return_value.AppendToTimeline.call_args.args[0][0]
            self.assertEqual(set(args), {'mediaPoolItem','trackIndex'})
            self.assertEqual(place(d,r,control),2)
            t.AddTrack.assert_called_once_with('subtitle')
            t.DeleteTrack.assert_not_called()

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_inspector_mismatch_rolls_back_only_new_track(self, imported):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.setup_scene(d)
            def mismatch(request):
                if request['command'] == 'edit':
                    raise RuntimeError('检查器目标不匹配')
            with self.assertRaisesRegex(RuntimeError,'目标不匹配'):
                place(d,r,mismatch)
            t.DeleteTrack.assert_called_once_with('subtitle',2)
            self.assertFalse((d/'placement-receipt.json').exists())

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_failed_position_readback_is_not_success(self, imported):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,_ = self.setup_scene(d)
            t.GetSelectedClips.return_value = [t.test_items[0]]
            with self.assertRaisesRegex(RuntimeError,'回读验证失败'):
                place(d,r,lambda request: None)
            t.DeleteTrack.assert_called_once()
            self.assertFalse((d/'placement-receipt.json').exists())

    @patch('vincisub.placement.time.sleep')
    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_misrouted_new_caption_is_removed_without_old_caption(self, imported, sleep):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,control = self.setup_scene(d)
            old = MagicMock()
            old.GetUniqueId.return_value = 'existing'
            appended = []
            p.GetMediaPool.return_value.AppendToTimeline.side_effect = lambda _: appended.append(t.test_items[0])
            t.GetItemListInTrack.side_effect = lambda kind, track: [old] + appended if track == 1 else []
            t.GetIsTrackEnabled.return_value = True
            with self.assertRaisesRegex(RuntimeError, '导入轨道'):
                place(d,r,control)
            t.DeleteClips.assert_called_once_with([t.test_items[0]],False)
            t.DeleteTrack.assert_called_once_with('subtitle',2)
            t.SetTrackEnable.assert_any_call('subtitle',1,True)
            self.assertFalse((d/'placement-receipt.json').exists())

    @patch('vincisub.placement.import_media', return_value=[object()])
    def test_final_readback_detects_earlier_caption_changed(self, imported):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); r,p,t,_,control = self.setup_scene(d)
            def changed(request):
                control(request)
                if request.get('text') == '乙':
                    t.test_items[0].GetEnd.return_value = 90100
            with self.assertRaisesRegex(RuntimeError, '最终验证失败'):
                place(d,r,changed)
            t.DeleteTrack.assert_called_once_with('subtitle',2)
            self.assertFalse((d/'placement-receipt.json').exists())

    def test_helper_launches_as_own_app_and_reports_permission_denial(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'native'/'ResolveCaptionBridge.swift'
            source.parent.mkdir(); source.touch()
            binary = root/'bin'/'VinciSub Helper.app'/'Contents'/'MacOS'/'ResolveCaptionBridge'
            binary.parent.mkdir(parents=True); binary.touch()
            def launch(args, **kwargs):
                self.assertEqual(args[:3], ['/usr/bin/open','-g','-n'])
                self.assertEqual(json.loads(Path(args[-2]).read_text(encoding='utf-8')), {'command':'preflight'})
                Path(args[-1]).write_text(json.dumps(dict(ok=False,message='需要辅助功能权限')),encoding='utf-8')
                return MagicMock(returncode=0)
            with patch('vincisub.placement.DATA',root), patch('vincisub.placement.ROOT',root), patch('vincisub.placement.sys.platform','darwin'), patch('vincisub.placement.subprocess.run',side_effect=launch):
                with self.assertRaisesRegex(RuntimeError,'辅助功能权限'):
                    bridge(dict(command='preflight'))
            self.assertFalse(list(root.glob('bridge-*')))
