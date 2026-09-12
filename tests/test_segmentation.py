import unittest
from types import SimpleNamespace as T
from dataclasses import asdict
from vincisub.subtitles import Caption, Word, make_captions, aligned_text_words, bridge_brief_gaps
from vincisub.realign import split_aligned
from vincisub.optimize import optimize


def measured(text):
    return [Word(c,i*.2,(i+1)*.2) for i,c in enumerate(text) if c.isalnum()]


def aligned(text):
    tokens=[T(text=c,start_time=i*.2,end_time=(i+1)*.2) for i,c in enumerate(text) if c.isalnum()]
    return aligned_text_words(tokens,text)


class SegmentationTests(unittest.TestCase):
    def test_new_generation_removes_punctuation_after_segmentation(self):
        from vincisub.worker import generated_rows
        text = '今天开始，明天继续。“苹果、香蕉——都要！”'
        words = aligned(text)
        expected = bridge_brief_gaps(make_captions(words))
        rows = generated_rows(words, 20)
        import unicodedata
        self.assertEqual(len(rows), len(expected))
        self.assertEqual([(r['start'], r['end']) for r in rows], [(c.start, c.end) for c in expected])
        self.assertEqual(''.join(r['text'] for r in rows), '今天开始明天继续苹果香蕉都要')
        self.assertFalse(any(unicodedata.category(c).startswith('P') for r in rows for c in r['text']))

    def test_new_generation_ignores_punctuation_only_output(self):
        from vincisub.worker import generated_rows
        self.assertEqual(generated_rows([Word('……', 0, 1)], 20), [])
        self.assertEqual(generated_rows([], 20), [])

    def test_unpunctuated_phrase_uses_measured_breath(self):
        words = [Word('我们今天去海边', 0, 1.4), Word('看看日落', 1.7, 2.8)]
        rows = make_captions(words)
        self.assertEqual(rows, [Caption(0, 1.4, '我们今天去海边'), Caption(1.7, 2.8, '看看日落')])
        # A short introductory word is not enough to justify a breath split.
        self.assertEqual(len(make_captions([Word('所以', 0, .4), Word('我们今天出发', .7, 2)])), 1)

    def test_aligner_pause_does_not_cut_inside_chinese_word(self):
        words = [Word('欢迎使用中文', 0, 1.2), Word('字', 1.2, 1.4),
                 Word('幕', 1.72, 1.9), Word('工具。', 1.9, 2.3)]
        self.assertEqual([r.text for r in make_captions(words)], ['欢迎使用中文字幕工具。'])
        # The size limit also backs off before an intact dictionary word.
        rows = make_captions(aligned('欢迎使用中文字幕工具。'), max_chars=7)
        self.assertEqual(''.join(r.text for r in rows), '欢迎使用中文字幕工具。')
        self.assertTrue(all(len(r.text) <= 7 and not r.text.endswith('字')
                            and not r.text.startswith('幕') for r in rows))

    def test_limit_prefers_pause_without_orphaning_short_fragments(self):
        words = [Word('今天', 0, .3), Word('出发', .3, .7),
                 Word('去看', .9, 1.2), Word('美丽', 1.2, 1.5), Word('日落', 1.5, 1.8)]
        rows = make_captions(words, max_chars=8)
        self.assertEqual([r.text for r in rows], ['今天出发', '去看美丽日落'])
        self.assertEqual([(r.start, r.end) for r in rows], [(0, .7), (.9, 1.8)])

    def test_number_grouping_is_not_a_comma_clause(self):
        rows = make_captions([Word('价格是44,', 0, 1.5), Word('900元。', 1.5, 2.3)])
        self.assertEqual([r.text for r in rows], ['价格是44,900元。'])

    def test_brief_gaps_do_not_change_onsets_long_pauses_or_last_end(self):
        original = [Caption(0, .3, '好！'), Caption(.5, 1, '出发。'), Caption(2, 3, '到了。')]
        result = bridge_brief_gaps(original)
        self.assertEqual(result, [Caption(0, .5, '好！'), original[1], original[2]])
        self.assertEqual(original[0].end, .3)
        self.assertEqual(bridge_brief_gaps([Caption(0, 1, '一'), Caption(1.201, 2, '二')])[0].end, 1)

    def test_resegmentation_bridges_only_internal_short_gaps(self):
        words = [Word('今天出发，', .1, 1.1), Word('明天回来。', 1.26, 2.3)]
        row = dict(start=0, end=2.4, text='今天出发，明天回来。')
        result = split_aligned(row, words, 20, 25)
        self.assertEqual(result[0]['end'], result[1]['start'])
        self.assertEqual(result[0]['start'], 0)
        self.assertEqual(result[-1]['end'], 2.4)

    def test_comma_clauses_and_quoted_sentence(self):
        text='杭州的夏天，三十九度，有人在奔跑，有人愁着订单。'
        captions=make_captions(aligned(text))
        self.assertEqual([r.text for r in captions],['杭州的夏天，','三十九度，','有人在奔跑，','有人愁着订单。'])
        quoted='“今天开始。”明天继续。'
        self.assertEqual([r.text for r in make_captions(aligned(quoted))],['“今天开始。”','明天继续。'])

    def test_short_intro_and_decimal(self):
        self.assertEqual([r.text for r in make_captions(aligned('所以，我们今天出发。'))],['所以，我们今天出发。'])
        self.assertEqual([r.text for r in make_captions(aligned('价格是3.5元。'))],['价格是3.5元。'])

    def test_prefers_prior_comma_over_mid_clause_limit(self):
        rows=make_captions(aligned('好的，今天我们一起出发'),max_chars=8)
        self.assertEqual(rows[0].text,'好的，')
        self.assertEqual(''.join(c.text for c in rows),'好的，今天我们一起出发')

    def test_split_before_punctuation_cleanup_measured_times(self):
        text='杭州的夏天，三十九度，有人在奔跑。'
        words=aligned(text);row=dict(start=0,end=words[-1].end,text=text)
        split=split_aligned(row,words,20,25)
        self.assertGreater(len(split),1)
        self.assertEqual(split[0]['start'],0);self.assertEqual(split[-1]['end'],row['end'])
        self.assertEqual(''.join(r['text'] for r in split),text)
        result=optimize(split,all_punctuation=True)
        self.assertTrue(all('，' not in r['text'] and '。' not in r['text'] for r in result))
        self.assertEqual([(r['start'],r['end']) for r in result],[(r['start'],r['end']) for r in split])

    def test_alignment_does_not_drop_unmatched_text(self):
        with self.assertRaises(ValueError):aligned_text_words([T(text='夏天',start_time=0,end_time=1)],'杭州的夏天')
        with self.assertRaises(ValueError):split_aligned(dict(start=0,end=.01,text='杭州的夏天，三十九度。'),aligned('杭州的夏天，三十九度。'),20,25)

    def test_preview_cache_changes_with_segmentation_settings(self):
        from vincisub.optimize_ui import OptimizeWindow
        window=OptimizeWindow.__new__(OptimizeWindow)
        window.items={'Tail':T(Value=.15),'ScriptOptimize':T(Checked=False),'Realign':T(Checked=False),'Resegment':T(Checked=True),'SegmentChars':T(Value=20)}
        original=window.key({'track':1})
        window.items['SegmentChars'].Value=12
        self.assertNotEqual(original,window.key({'track':1}))
        window.items['Resegment'].Checked=False
        self.assertFalse(window.needs_model())
