import unittest
from types import SimpleNamespace

from opencc import OpenCC

from vincisub.worker import with_punctuation


class WorkerTests(unittest.TestCase):
    def test_simplified_conversion_preserves_alignment_and_punctuation(self):
        items = [SimpleNamespace(text="歡", start_time=.1, end_time=.3), SimpleNamespace(text="迎", start_time=.3, end_time=.5)]
        words = list(with_punctuation(items, "歡迎！", OpenCC("t2s").convert))
        self.assertEqual([w.text for w in words], ["欢", "迎！"])
        self.assertEqual((words[0].start, words[1].end), (.1, .5))
