import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from vincisub.audio import chunks, normalize


class AudioTests(unittest.TestCase):
    def test_chunks_cover_every_sample_once(self):
        original = np.zeros(16000 * 61, dtype="float32")
        pieces = list(chunks(original))
        self.assertGreater(len(pieces), 2)
        np.testing.assert_array_equal(np.concatenate([p[1] for p in pieces]), original)
        count = 0
        for offset, piece in pieces:
            self.assertAlmostEqual(offset, count / 16000)
            self.assertLessEqual(len(piece), 25 * 16000)
            count += len(piece)

    def test_ffmpeg_normalizes_sample_rate_and_channels(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "input.wav", Path(folder) / "output.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
                audio.writeframes(b"\0" * 44100 * 4)
            self.assertAlmostEqual(normalize(source, target), 1, places=2)
            with wave.open(str(target)) as result:
                self.assertEqual((result.getnchannels(), result.getframerate(), result.getsampwidth()), (1, 16000, 2))

    def test_invalid_media_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.bin"
            source.write_text("not audio")
            with self.assertRaisesRegex(ValueError, "无法读取音轨"):
                normalize(source, Path(folder) / "output.wav")
