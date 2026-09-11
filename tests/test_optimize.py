import unittest
from vincisub.optimize import clean_text,optimize


class OptimizeTests(unittest.TestCase):
    def test_endings_preserve_internal_punctuation_and_quotes(self):
        self.assertEqual(clean_text('他说：“甲、乙——都行。”，',True),'他说：“甲、乙——都行”')
        self.assertEqual(clean_text('3.14，没错。',True),'3.14，没错')
        self.assertEqual(clean_text('Really?',True),'Really?')
        self.assertEqual(clean_text('English.',True),'English')
        self.assertEqual(clean_text('He said "yes."',True),'He said "yes"')

    def test_all_punctuation_and_empty_protection(self):
        self.assertEqual(clean_text('“甲、乙”——好！',True,True),'甲乙好')
        self.assertEqual(clean_text('……',True,True),'……')

    def test_fill_only_short_positive_gaps_and_keep_input(self):
        rows=[dict(start=0,end=1,text='甲。'),dict(start=1.5,end=2,text='乙，'),dict(start=4,end=5,text='丙')]
        result=optimize(rows,fill_gaps=True,max_gap=.5)
        self.assertEqual([r['end'] for r in result],[1.5,2,5])
        self.assertEqual(rows[0]['end'],1)
        self.assertEqual(rows[0]['text'],'甲。')
        self.assertEqual(optimize(result,fill_gaps=True),result)

    def test_no_options_and_invalid_threshold(self):
        rows=[dict(start=0,end=1,text='甲。')]
        self.assertEqual(optimize(rows,ending=False),rows)
        for gap in [-1,11,float('nan')]:
            with self.assertRaises(ValueError):optimize(rows,max_gap=gap)
