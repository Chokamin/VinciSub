"""Read-only checks against a configured public GitHub release repository."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import __version__
from .storage import ROOT


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value or '')
    if not match:
        raise ValueError('版本号需使用 v1.2.3 格式的正式版本。')
    return tuple(map(int, match.groups()))


def check(root=ROOT, current=__version__, opener=urlopen):
    try:
        repository = json.loads((root / 'update-source.json').read_text(encoding='utf-8'))['repository'].strip()
        if not repository:
            return dict(message='尚未配置更新源。发布到 GitHub 后即可启用检查更新。', notes='', url='')
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('更新源格式应为 GitHub 用户名/仓库名。')
        request = Request(f'https://api.github.com/repos/{repository}/releases/latest', headers={
            'Accept': 'application/vnd.github+json', 'User-Agent': 'VinciSub/' + current,
        })
        with opener(request, timeout=10) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('更新信息过大，请稍后重试。')
        release = json.loads(raw)
        if release.get('draft') or release.get('prerelease'):
            raise ValueError('更新源未返回正式发布版本。')
        tag = release['tag_name']
        newer = version(tag) > version(current)
        return dict(message=f'发现新版本 {tag}' if newer else f'当前无需更新（最新正式版 {tag}）。',
                    notes=str(release.get('body') or '暂无更新说明。')[:12000],
                    url=f'https://github.com/{repository}/releases/tag/{quote(tag, safe="")}' if newer else '')
    except HTTPError as error:
        message = '尚无公开正式版本，或发布仓库不可访问。' if error.code == 404 else 'GitHub 暂时无法响应，请稍后重试。'
    except (URLError, TimeoutError, OSError):
        message = '检查失败，请检查网络或更新源配置后重试。'
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        message = '更新信息无效：' + (str(error) if isinstance(error, ValueError) else '请检查发布源配置。')
    return dict(message=message, notes='', url='')
