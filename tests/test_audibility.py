import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from vincisub.audibility import audible_tracks, read_flags


class AudibilityTests(unittest.TestCase):
    def resolve_tracks(self, flags, enabled=None):
        resolve, timeline = MagicMock(), MagicMock()
        resolve.GetVersion.return_value = [21, 1, 0, 14]
        timeline.GetIsTrackEnabled.side_effect = enabled or [not f & 2 for f in flags]
        with patch('vincisub.audibility.read_flags', return_value=flags):
            result = audible_tracks(resolve, timeline, len(flags))
        path = Path(timeline.Export.call_args.args[0])
        self.assertFalse(path.parent.exists())
        timeline.SetTrackEnable.assert_not_called()
        return result

    def test_no_solo_uses_all_unmuted_tracks_including_locked(self):
        self.assertEqual(self.resolve_tracks([0, 2, 1, 0]), [1, 3, 4])

    def test_two_solo_tracks_exclude_other_enabled_tracks(self):
        self.assertEqual(self.resolve_tracks([32, 0, 32, 2]), [1, 3])

    def test_muted_solo_does_not_fall_back_to_other_tracks(self):
        with self.assertRaisesRegex(ValueError, '没有可听音轨'):
            self.resolve_tracks([34, 0])

    def test_all_muted_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, '没有可听音轨'):
            self.resolve_tracks([2, 2])

    def test_state_change_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '发生变化'):
            self.resolve_tracks([0, 0], [True, False])

    def test_unverified_version_and_failed_export_do_not_guess(self):
        r, t = MagicMock(), MagicMock()
        r.GetVersion.return_value = [20, 3]
        with self.assertRaisesRegex(ValueError, '21.1'):
            audible_tracks(r, t, 2)
        t.Export.assert_not_called()
        r.GetVersion.return_value = [21, 1]
        t.Export.return_value = False
        with self.assertRaisesRegex(ValueError, '无法读取'):
            audible_tracks(r, t, 2)

    def test_archive_selects_root_sequence_not_nested_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'tracks.drt'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('project.xml', '<P><TimelineHandleVec><Element>root</Element></TimelineHandleVec></P>')
                z.writestr('MediaPool/Master/MpFolder.xml', '<P><Sm2Timeline DbId="root"><Sequence><Sm2Sequence DbId="seq"><ListMgt::LmVersion/></Sm2Sequence></Sequence></Sm2Timeline></P>')
                for name, seq, flag in [('root','seq',32), ('nested','other',0)]:
                    z.writestr(f'SeqContainer/{name}.xml', f'<P><AudioTrackVec><Element><Sm2TiTrack><Sequence>{seq}</Sequence><Flags>{flag}</Flags></Sm2TiTrack></Element></AudioTrackVec></P>')
            self.assertEqual(read_flags(path, 1), [32])
            with self.assertRaisesRegex(ValueError, '数量不一致'):
                read_flags(path, 2)
