import unittest
from vincisub.text_units import clean_generated_text, display_length
from vincisub.subtitles import Word, make_captions
from vincisub.worker import generated_rows
from vincisub.realign import split_aligned


class TextUnitTests(unittest.TestCase):
    def test_interior_instant_token_uses_close_preceding_measurement(self):
        from vincisub.subtitles import merge_instant_words
        words = [Word('微', 2.4, 2.64), Word('的', 2.72, 2.72), Word('差异', 2.88, 3.36)]
        self.assertEqual(merge_instant_words(words), [Word('微的', 2.4, 2.72), words[-1]])
        self.assertEqual(''.join(r['text'] for r in generated_rows(words, 20)), '微的差异')
        with self.assertRaises(ValueError):
            merge_instant_words([Word('微', 2.4, 2.64), Word('的', 3, 3), Word('差异', 3.4, 4)])

    def test_cleanup_keeps_written_values_but_removes_sentence_punctuation(self):
        text = '尺寸1/1.1英寸，延迟0.1毫秒；范围12-13档，时间6:44，亮度50%，温度-5度。'
        self.assertEqual(clean_generated_text(text),
                         '尺寸1/1.1英寸延迟0.1毫秒范围12-13档时间6:44亮度50%温度-5度')
        self.assertEqual(clean_generated_text('售价2,000元。'), '售价2,000元')

    def test_cleanup_keeps_identifiers_and_word_separation(self):
        self.assertEqual(clean_generated_text('“USB-C、C++、C#、v1.2。”'), 'USB-C C++ C# v1.2')
        self.assertEqual(clean_generated_text("Ready,go! Don't stop."), "Ready go Don't stop")
        self.assertEqual(clean_generated_text('“你好！”——再见。'), '你好再见')
        self.assertEqual(clean_generated_text('……'), '')

    def test_numeric_unit_is_not_split_at_size_limit(self):
        words = [Word('我们测得', 0, .8), Word('0.1', .8, 1),
                 Word('毫秒', 1.1, 1.3), Word('延迟', 1.3, 1.6)]
        rows = generated_rows(words, 6)
        self.assertEqual([r['text'] for r in rows], ['我们测得', '0.1毫秒延迟'])
        self.assertEqual(rows[0]['start'], 0)
        self.assertEqual(rows[-1]['end'], 1.6)

    def test_vocabulary_protects_names_without_leaking_to_other_jobs(self):
        name = '星河映像实验室'
        text = '欢迎来到' + name + '参观'
        words = [Word(c, i*.1, (i+1)*.1) for i, c in enumerate(text)]
        protected = generated_rows(words, 6, [name])
        self.assertTrue(any(name in r['text'] for r in protected))
        self.assertEqual(''.join(r['text'] for r in protected), text)
        unprotected = generated_rows(words, 6)
        self.assertFalse(any(name in r['text'] for r in unprotected))
        old = dict(start=0, end=words[-1].end, text=text)
        split = split_aligned(old, words, 6, 25, [name])
        self.assertTrue(any(name in r['text'] for r in split))
        self.assertEqual(split[0]['start'], old['start'])
        self.assertEqual(split[-1]['end'], old['end'])

    def test_mixed_language_uses_display_width_without_gluing_english(self):
        words = [Word('今天', 0, .4), Word('DaVinci', .4, 1),
                 Word('Resolve', 1, 1.5), Word('很好用', 1.5, 2)]
        self.assertEqual([r.text for r in make_captions(words, max_chars=14)], ['今天DaVinci Resolve很好用'])
        self.assertEqual(display_length('字幕ABC123'), 5)

    def test_name_protection_does_not_bridge_a_long_silence(self):
        rows = make_captions([Word('星河', 0, .5), Word('映像', 2, 2.5)], protected_terms=['星河映像'])
        self.assertEqual([r.text for r in rows], ['星河', '映像'])
        self.assertEqual(rows[0].end, .5)
