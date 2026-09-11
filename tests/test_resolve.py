import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vincisub.resolve import import_media, import_subtitle


class ResolveTests(unittest.TestCase):
    def context(self):
        resolve, project, timeline = MagicMock(), MagicMock(), MagicMock()
        project.GetCurrentTimeline.return_value = timeline
        project.GetUniqueId.return_value = "project-a"
        timeline.GetUniqueId.return_value = "timeline-a"
        timeline.GetStartFrame.return_value = 90000
        timeline.GetEndFrame.return_value = 90250
        project.IsRenderingInProgress.return_value = False
        project.GetRenderJobStatus.return_value = {"JobStatus": "Complete"}
        return resolve, project, timeline

    def test_import_refuses_wrong_timeline(self):
        resolve, project, _ = self.context()
        with patch("vincisub.resolve.connect", return_value=(resolve, project)), self.assertRaises(ValueError):
            import_subtitle(Path("sample.srt"), dict(project_id="project-a", timeline_id="timeline-b"))
        project.GetMediaPool.assert_not_called()

    def test_import_uses_legacy_path_when_clip_info_is_not_supported(self):
        pool = MagicMock()
        pool.ImportMedia.side_effect = [[], ["subtitle"]]
        self.assertEqual(import_media(pool, Path("sub.srt")), ["subtitle"])
        self.assertEqual(pool.ImportMedia.call_args.args[0], ["sub.srt"])

    def test_import_failure_is_reported(self):
        resolve, project, _ = self.context()
        project.GetMediaPool.return_value.ImportMedia.return_value = []
        with patch("vincisub.resolve.connect", return_value=(resolve, project)), self.assertRaises(RuntimeError):
            import_subtitle(Path("sub.srt"))
