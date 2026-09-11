import tempfile
import unittest
from pathlib import Path
from vincisub.vocabulary import parse,save,load,context


class VocabularyTests(unittest.TestCase):
    def test_parse_separators_deduplicates_preserves_phrases(self):
        self.assertEqual(parse(' 小蚕，奇奇字幕\nDaVinci Resolve;小蚕'),['小蚕','奇奇字幕','DaVinci Resolve'])

    def test_save_load_disable_keeps_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            self.assertEqual(load(data)['terms'],[])
            save(data,'奇奇字幕\n小蚕',False)
            self.assertEqual(load(data),dict(enabled=False,terms=['奇奇字幕','小蚕']))
            save(data,'',True)
            self.assertEqual(load(data)['terms'],[])

    def test_context_and_limits(self):
        self.assertEqual(context([]),'')
        self.assertEqual(context(['小蚕','奇奇字幕']),'小蚕，奇奇字幕')
        for text in ['x'*65,','.join(str(n) for n in range(101)),'a\x00b']:
            with self.assertRaises(ValueError):parse(text)

    def test_invalid_save_does_not_replace_dictionary(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);save(data,'小蚕')
            with self.assertRaises(ValueError):save(data,'x'*65)
            self.assertEqual(load(data)['terms'],['小蚕'])
