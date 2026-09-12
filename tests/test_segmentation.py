import unittest
from types import SimpleNamespace as T
from dataclasses import asdict
from vincisub.subtitles import Word, make_captions, aligned_text_words
from vincisub.realign import split_aligned
from vincisub.optimize import optimize


def measured(text):
    return [Word(c,i*.2,(i+1)*.2) for i,c in enumerate(text) if c.isalnum()]


def aligned(text):
    tokens=[T(text=c,start_time=i*.2,end_time=(i+1)*.2) for i,c in enumerate(text) if c.isalnum()]
    return aligned_text_words(tokens,text)


class SegmentationTests(unittest.TestCase):
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
