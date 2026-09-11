import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class NativeEntryTests(unittest.TestCase):
    def test_resolve_host_without_dunder_file_launches_native_ui(self):
        entry = Path(__file__).resolve().parents[1] / 'scripts/VinciSub.py'
        context = dict(resolve=object(), fusion=object(), bmd=object())
        with patch('vincisub.native_ui.launch') as launch:
            exec(compile(entry.read_text(encoding='utf-8'), str(entry), 'exec'), context)
        launch.assert_called_once_with(context['resolve'], context['fusion'], context['bmd'])

    def test_ui_import_does_not_load_inference_or_http_server(self):
        code = "import sys; import vincisub.native_ui; assert not {'torch', 'qwen_asr', 'http.server'} & sys.modules.keys()"
        subprocess.run([sys.executable, '-c', code], check=True)
