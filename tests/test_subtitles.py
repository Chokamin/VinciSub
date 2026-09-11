import unittest
from dataclasses import asdict

from vincisub.subtitles import Caption, Word, make_captions, timestamp, to_srt, validate_captions


class SubtitleTests(unittest.TestCase):
    def test_chinese_sentence_and_pause_boundaries(self):
        words = [Word("你", 0.1, 0.3), Word("好。", 0.3, 0.6), Word("世", 1.4, 1.6), Word("界", 1.6, 1.9)]
        captions = make_captions(words)
        self.assertEqual(captions, [Caption(0.1, 0.6, "你好。"), Caption(1.4, 1.9, "世界")])

    def test_mixed_english_words_have_spaces(self):
        words = [Word("用", 0, .2), Word("DaVinci", .2, .8), Word("Resolve", .8, 1.2), Word("剪辑", 1.2, 2)]
        self.assertEqual(make_captions(words)[0].text, "用DaVinci Resolve剪辑")

    def test_length_splitting_keeps_original_timings(self):
        words = [Word(c, i, i + .9) for i, c in enumerate("今天我们一起学习生成中文字幕")]
        captions = make_captions(words, max_chars=6, max_duration=20)
        self.assertEqual(captions[0].text, "今天我们一起")
        self.assertEqual(captions[1].start, 6)
        self.assertEqual("".join(c.text for c in captions), "今天我们一起学习生成中文字幕")

    def test_export_rollover_offset_and_unicode(self):
        captions = [Caption(.9996, 2, "简体中文")]
        self.assertEqual(timestamp(.9996), "00:00:01,000")
        self.assertEqual(to_srt(captions, 3600), "1\n01:00:01,000 --> 01:00:02,000\n简体中文\n")

    def test_rejects_invalid_or_overlapping_times(self):
        for start, end in [(-1, 1), (2, 1), (1, 1), (float("nan"), 2), (0, float("inf"))]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_captions([dict(start=start, end=end, text="测试")])
        with self.assertRaises(ValueError):
            validate_captions([dict(start=0, end=2, text="一"), dict(start=1, end=3, text="二")])
        with self.assertRaises(ValueError):
            to_srt([Caption(0, 1, "测试")], -1)

    def test_blank_lines_cannot_inject_srt_blocks(self):
        checked = validate_captions([dict(start=0, end=1, text="第一行\n\n第二行")])
        self.assertEqual(checked[0].text, "第一行\n第二行")
        for text in ["", "  ", "a\x00b"]:
            with self.assertRaises(ValueError):
                validate_captions([dict(start=0, end=1, text=text)])

    def test_zero_duration_model_words_fail_instead_of_invented_timing(self):
        with self.assertRaises(ValueError):
            make_captions([Word("错误", 1, 1)])

    def test_coincident_zero_duration_characters_keep_text_and_measured_span(self):
        captions = make_captions([Word("我", 3.84, 3.84), Word("们", 3.84, 4.16)])
        self.assertEqual(captions, [Caption(3.84, 4.16, "我们")])
        with self.assertRaises(ValueError):
            make_captions([Word("我", 1, 1), Word("们", 3, 4)])

    def test_small_model_overlap_is_trimmed(self):
        captions = make_captions([Word("一。", 0, 1), Word("二。", .99, 2)])
        self.assertEqual(captions[1].start, 1)
        validate_captions([asdict(c) for c in captions])
