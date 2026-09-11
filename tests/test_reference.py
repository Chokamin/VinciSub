import tempfile
import unittest
from pathlib import Path
from vincisub import reference


class ReferenceTests(unittest.TestCase):
    def test_save_load_disable_preserves_text(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            self.assertFalse(reference.load(data)['enabled'])
            reference.save(data,' 第一段\r\n第二段 ',True)
            self.assertEqual(reference.load(data),dict(enabled=True,text='第一段\n第二段'))
            reference.save(data,reference.load(data)['text'],False)
            self.assertEqual(reference.load(data)['text'],'第一段\n第二段')

    def test_invalid_save_preserves_previous(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);reference.save(data,'旧脚本',True)
            for text in ['字'*6001,'错误\x00',None]:
                with self.assertRaises(ValueError):reference.save(data,text,True)
                self.assertEqual(reference.load(data)['text'],'旧脚本')

    def test_context_combines_hints_and_keeps_audio_priority(self):
        self.assertEqual(reference.context(['专名'],''),'专名')
        value=reference.context(['奇奇字幕'],'欢迎体验奇奇字幕。')
        self.assertIn('奇奇字幕',value)
        self.assertIn('欢迎体验奇奇字幕。',value)
        self.assertIn('不补写未说出的脚本',value)
        self.assertEqual(reference.context([],''),'')

    def test_unalignable_reference_retries_audio_with_vocabulary(self):
        from unittest.mock import Mock
        from vincisub.worker import recognize_with_reference_fallback
        recognize=Mock(side_effect=[ValueError('bad alignment'),['audio words']]);warnings=[]
        result=recognize_with_reference_fallback(recognize,'script hint',dict(reference_script='稿',vocabulary=['专名']),warnings)
        self.assertEqual(result,['audio words'])
        self.assertEqual(recognize.call_args.args,('专名',))
        self.assertEqual(len(warnings),1)
        with self.assertRaises(ValueError):
            recognize_with_reference_fallback(Mock(side_effect=ValueError()),'',{},[])
