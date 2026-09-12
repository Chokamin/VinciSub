import unittest
from types import SimpleNamespace as T
from vincisub.realign import aligned_bounds,reconcile


class RealignTests(unittest.TestCase):
    def test_bounds_and_invalid_timestamps(self):
        row=dict(start=1,end=2,text='你好')
        self.assertEqual(aligned_bounds([T(start_time=.8,end_time=2.2)],0,3,row),(.8,2.2))
        for tokens in [[],[T(start_time=1,end_time=1)],[T(start_time=float('nan'),end_time=2)]]:
            with self.assertRaises(ValueError):aligned_bounds(tokens,0,3,row)

    def test_tail_clipped_at_next_start_and_text_preserved(self):
        rows=[dict(start=1,end=2,text='原文'),dict(start=2.3,end=3,text='第二句')]
        proposed=[dict(rows[0],start=.9,end=2.2),dict(rows[1])]
        result,failed=reconcile(rows,proposed,[],.15,4,25)
        self.assertLessEqual(result[0]['end'],result[1]['start'])
        self.assertEqual([r['text'] for r in result],['原文','第二句'])
        self.assertEqual(rows[0]['start'],1)

    def test_conflicts_restore_original_and_failed_stay_unchanged(self):
        rows=[dict(start=1,end=2,text='甲'),dict(start=3,end=4,text='乙')]
        result,failed=reconcile(rows,[dict(rows[0],end=3.5),dict(rows[1])],[],.15,5,25)
        self.assertEqual(result,rows);self.assertEqual(failed,[0,1])
        result,failed=reconcile(rows,rows,[0],.15,5,25)
        self.assertEqual(result[0],rows[0])

    def test_script_changes_invalidate_preview_and_require_text(self):
        from vincisub.optimize_ui import OptimizeWindow
        window=OptimizeWindow.__new__(OptimizeWindow)
        from unittest.mock import patch
        window.jobs=T(data='test-data')
        window.items={'ScriptOptimize':T(Checked=True),'Realign':T(Checked=False),'Tail':T(Value=.15),'Resegment':T(Checked=False),'SegmentChars':T(Value=20)}
        with patch('vincisub.optimize_ui.reference.load') as load:
            load.return_value=dict(text='参考稿',enabled=False)
            key=window.key({'track':1})
            self.assertEqual(key[4],'参考稿')
            load.return_value=dict(text='新参考稿',enabled=True)
            self.assertNotEqual(key,window.key({'track':1}))
            load.return_value=dict(text='',enabled=True)
            with self.assertRaisesRegex(ValueError,'主面板'):window.key({'track':1})
            window.items['ScriptOptimize'].Checked=False
            self.assertEqual(window.key({'track':1})[4],'')

    def test_cancel_stops_computation_without_applying(self):
        from unittest.mock import Mock
        from vincisub.optimize_ui import OptimizeWindow
        window=OptimizeWindow.__new__(OptimizeWindow)
        process=Mock();process.poll.return_value=None
        window.process=process;window.window=Mock();window.parent=T(Enabled=False);window.apply=Mock()
        window.dismiss()
        process.terminate.assert_called_once()
        self.assertIsNone(window.process)
        self.assertTrue(window.parent.Enabled)
        window.apply.assert_not_called()
