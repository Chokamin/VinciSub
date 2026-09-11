"""Native Resolve UI entry point. Install as a symlink so the project is found."""

import inspect
import pathlib
import sys

ROOT = pathlib.Path(globals().get("__file__", inspect.currentframe().f_code.co_filename)).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vincisub.native_ui import launch

# These globals are supplied by Resolve's Workspace > Scripts host.
launch(resolve, fusion, bmd)
