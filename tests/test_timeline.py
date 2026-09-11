import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from vincisub.timeline import selection, snapshot, decode, source_seconds


class TimelineTests(unittest.TestCase):
    def timeline(self, marks=None):
        t = MagicMock()
        t.GetSetting.return_value = 25
        t.GetStartFrame.return_value = 90000
        t.GetEndFrame.return_value = 92500
        t.GetMarkInOut.return_value = marks or {'audio': {}, 'video': {}}
        return t

    def test_no_marks_uses_entire_timeline_at_nonzero_start(self):
        result = selection(self.timeline())
        self.assertEqual((result['offset'], result['duration']), (0, 100))
        self.assertFalse(result['marked'])

    def test_marks_are_relative_and_out_frame_is_inclusive(self):
        result = selection(self.timeline({'audio': {'in': 25, 'out': 49}}))
        self.assertEqual((result['start'], result['end']), (90025, 90050))
        self.assertEqual((result['offset'], result['duration']), (1, 1))

    def test_video_marks_and_one_sided_marks(self):
        result = selection(self.timeline({'audio': {}, 'video': {'in': 50}}))
        self.assertEqual((result['offset'], result['duration']), (2, 98))
        result = selection(self.timeline({'audio': {'out': 24}}))
        self.assertEqual(result['duration'], 1)

    def test_audio_marks_take_precedence(self):
        result = selection(self.timeline({'audio': {'in': 25, 'out': 49}, 'video': {'in': 100, 'out': 200}}))
        self.assertEqual(result['duration'], 1)

    def test_invalid_range_is_not_silently_whole_timeline(self):
        with self.assertRaises(ValueError):
            selection(self.timeline({'audio': {'in': 100, 'out': 50}}))

    def test_source_timecode_dropframe(self):
        self.assertAlmostEqual(source_seconds('01:00:00;00', 30000/1001), 3599.9964)

    def test_decode_crops_channel_and_preserves_silence_and_position(self):
        rate = 16000
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'stereo.wav'
            # Only the second second has signal in channel 2.
            audio = np.zeros((rate*3, 2), dtype='<i2')
            audio[rate:rate*2, 1] = 12000
            with wave.open(str(source), 'wb') as stream:
                stream.setparams((2,2,rate,0,'NONE','not compressed'))
                stream.writeframes(audio.tobytes())
            plan = {'duration': 3, 'clips': [{'path':str(source), 'source_start':1, 'duration':1, 'speed':1, 'offset':1, 'channels':[1]}]}
            output, _ = decode(plan)
            self.assertLess(abs(output[:rate]).max(), .0001)
            self.assertGreater(output[rate+100:rate*2-100].mean(), .3)
            self.assertLess(abs(output[rate*2:]).max(), .0001)
            self.assertEqual(list(Path(folder).iterdir()), [source])
            plan['clips'][0]['channels'] = [0]
            other, _ = decode(plan)
            self.assertLess(abs(other).max(), .0001)

    def test_snapshot_only_reads_selected_track_and_clips_to_marks(self):
        with tempfile.NamedTemporaryFile() as source:
            r, project, t = MagicMock(), MagicMock(), self.timeline({'audio': {'in':25, 'out':49}})
            r.GetProjectManager.return_value.GetCurrentProject.return_value = project
            project.GetCurrentTimeline.return_value = t
            t.GetTrackCount.return_value = 2
            item = MagicMock()
            item.GetStart.return_value, item.GetEnd.return_value = 90000, 90100
            item.GetClipEnabled.return_value = True
            item.GetSourceStartTime.return_value, item.GetSourceEndTime.return_value = 3602, 3605.96
            media = item.GetMediaPoolItem.return_value
            media.GetClipProperty.side_effect = lambda key: {'File Path':source.name,'FPS':25,'Start TC':'01:00:00:00'}[key]
            item.GetSourceAudioChannelMapping.return_value = json.dumps({'embedded_audio_channels':2,'track_mapping':{'1':{'channel_idx':[2],'mute':False}}})
            t.GetItemListInTrack.return_value = [item]
            result = snapshot(r, 2)
            t.GetItemListInTrack.assert_called_once_with('audio', 2)
            self.assertEqual(result['clips'][0]['source_start'], 3)
            self.assertEqual(result['clips'][0]['channels'], [1])
            self.assertEqual(result['clips'][0]['duration'], 1)
            r.OpenPage.assert_not_called()
            project.AddRenderJob.assert_not_called()

    def test_snapshot_auto_collects_both_tracks(self):
        with tempfile.NamedTemporaryFile() as source:
            r, t = MagicMock(), self.timeline()
            r.GetProjectManager.return_value.GetCurrentProject.return_value.GetCurrentTimeline.return_value = t
            t.GetTrackCount.return_value = 3
            item = MagicMock()
            item.GetStart.return_value, item.GetEnd.return_value = 90000, 90025
            item.GetClipEnabled.return_value = True
            item.GetSourceStartTime.return_value, item.GetSourceEndTime.return_value = 0, .96
            item.GetMediaPoolItem.return_value.GetClipProperty.side_effect = lambda k: {'File Path':source.name, 'FPS':25, 'Start TC':'00:00:00:00'}[k]
            item.GetSourceAudioChannelMapping.return_value = json.dumps({'embedded_audio_channels':1, 'track_mapping':{'1':{'channel_idx':[1]}}})
            t.GetItemListInTrack.return_value = [item]
            with patch('vincisub.timeline.audible_tracks', return_value=[1,3]):
                plan = snapshot(r)
            self.assertEqual(plan['track_indices'], [1,3])
            self.assertEqual([c['track_index'] for c in plan['clips']], [1,3])
            self.assertEqual([call.args for call in t.GetItemListInTrack.call_args_list], [('audio',1), ('audio',3)])
