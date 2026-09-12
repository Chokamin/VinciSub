import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from vincisub.updates import check
from vincisub import __version__


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source('owner/repo')

    def source(self, repo):
        (self.root/'update-source.json').write_text(json.dumps(dict(repository=repo)))

    def fetch(self, tag, **extra):
        return Mock(return_value=io.BytesIO(json.dumps(dict(tag_name=tag, body='更新说明', **extra)).encode()))

    def test_new_release_numeric_comparison_and_trusted_link(self):
        opener = self.fetch('v0.10.0', html_url='https://untrusted.example')
        result = check(self.root, '0.9.0', opener)
        self.assertEqual(result['url'], 'https://github.com/owner/repo/releases/tag/v0.10.0')
        self.assertEqual(result['notes'], '更新说明')
        self.assertEqual(opener.call_args.kwargs['timeout'], 10)

    def test_equal_and_older_do_not_offer_update(self):
        for tag in ['0.1.0', 'v0.0.9']:
            self.assertFalse(check(self.root, '0.1.0', self.fetch(tag))['url'])

    def test_missing_source_never_calls_network(self):
        self.source('')
        opener = Mock()
        self.assertIn('尚未配置', check(self.root, opener=opener)['message'])
        opener.assert_not_called()

    def test_errors_and_invalid_releases(self):
        for error in [URLError('offline'), TimeoutError(), HTTPError('',404,'',{},None), HTTPError('',403,'',{},None)]:
            result = check(self.root, opener=Mock(side_effect=error))
            self.assertFalse(result['url'])
            self.assertNotIn('无需更新', result['message'])
        for tag, extra in [('v2.0.0-beta', {}), ('v2.0.0', {'prerelease':True}), ('v2.0.0', {'draft':True})]:
            self.assertIn('无效', check(self.root, opener=self.fetch(tag, **extra))['message'])
        self.assertFalse(check(self.root, opener=Mock(return_value=io.BytesIO(b'bad json')))['url'])

    def test_invalid_source_and_versions_match(self):
        self.source('owner/repo/evil')
        opener = Mock()
        self.assertIn('格式', check(self.root, opener=opener)['message'])
        opener.assert_not_called()
        import tomllib
        from vincisub.storage import ROOT
        self.assertEqual(tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version'], __version__)

    def test_published_source(self):
        from vincisub.storage import ROOT
        self.assertEqual(json.loads((ROOT/'update-source.json').read_text())['repository'], 'Chokamin/VinciSub')

    def test_current_release_is_detectable_by_previous_version(self):
        from vincisub.storage import ROOT
        notes = (ROOT/'RELEASE_NOTES.md').read_text(encoding='utf-8')
        self.assertIn('v' + __version__, notes.splitlines()[0])
        result = check(self.root, '0.1.0', self.fetch('v' + __version__))
        self.assertTrue(result['url'].endswith('/v' + __version__))
        self.assertFalse(check(self.root, __version__, self.fetch('v' + __version__))['url'])
