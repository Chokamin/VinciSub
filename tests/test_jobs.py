import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vincisub.jobs import Jobs
from vincisub.storage import write_json


class JobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.jobs = Jobs(self.temp.name)
        self.jobs.directory = self.jobs.jobs / ('a' * 32)
        self.jobs.directory.mkdir()
        write_json(self.jobs.directory / 'status.json', {'state': 'done', 'message': '中文字幕已完成'})
        write_json(self.jobs.directory / 'result.json', {'duration': 3, 'captions': [{'start': 0, 'end': 2, 'text': '你好，世界。'}], 'offset': 0})

    def test_chinese_roundtrip_save_and_srt_export(self):
        self.jobs.save([{'start': .2, 'end': 2.5, 'text': '修改后的字幕'}], .5)
        text = self.jobs.export().read_text(encoding='utf-8-sig')
        self.assertIn('00:00:00,700 --> 00:00:03,000', text)
        self.assertIn('修改后的字幕', text)

    def test_invalid_edit_does_not_destroy_result(self):
        previous = self.jobs.result()
        with self.assertRaises(ValueError):
            self.jobs.save([{'start': 0, 'end': 4, 'text': '超出音频'}])
        self.assertEqual(previous, self.jobs.result())

    def test_running_job_is_marked_interrupted_on_reopen(self):
        self.jobs._status('running', '识别中')
        write_json(Path(self.temp.name) / 'native-latest.json', {'id': self.jobs.directory.name})
        self.assertEqual(Jobs(self.temp.name).status()['state'], 'error')

    def test_missing_environment_fails_before_starting(self):
        self.jobs.python = Path(self.temp.name) / 'missing'
        with self.assertRaisesRegex(RuntimeError, 'setup.sh'):
            self.jobs.start()

    def test_all_json_reads_specify_utf8_in_resolve_ascii_locale(self):
        original = Path.read_text
        def strict(path, *args, **kwargs):
            self.assertEqual(kwargs.get('encoding'), 'utf-8')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', strict):
            self.assertEqual(self.jobs.status()['message'], '中文字幕已完成')
            self.assertEqual(self.jobs.result()['captions'][0]['text'], '你好，世界。')

    def test_cancel_terminates_worker_process_group(self):
        import subprocess
        import sys
        self.jobs.process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        self.addCleanup(lambda: self.jobs.process.kill() if self.jobs.busy() else None)
        self.jobs._status('running', '识别中')
        self.jobs.cancel()
        self.assertFalse(self.jobs.busy())
        self.assertEqual(self.jobs.status()['state'], 'cancelled')

    @patch('vincisub.jobs.subprocess.Popen')
    @patch('vincisub.jobs.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_vocabulary_is_snapshotted_in_request(self,which,popen):
        source=Path(self.temp.name)/'input.wav';source.write_bytes(b'test')
        words=['小蚕','小蚕','奇奇字幕']
        self.jobs.start(path=source,vocabulary=words,reference_script="参考口播稿")
        words.clear()
        request=json.loads((self.jobs.directory/'request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['vocabulary'],['小蚕','奇奇字幕'])
        self.assertEqual(request['reference_script'],'参考口播稿')
