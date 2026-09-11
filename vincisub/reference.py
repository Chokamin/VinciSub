"""Optional spoken-script context; never substitute it for recognized audio."""
import json
from .storage import write_json
from .vocabulary import context as vocabulary_context


def validate(text):
    if not isinstance(text,str):
        raise ValueError('参考脚本必须为文本。')
    text=text.replace('\r\n','\n').replace('\r','\n').strip()
    if len(text)>6000:
        raise ValueError('参考脚本最多 6000 字，请保留与本次音频相关的内容。')
    if any(ord(c)<32 and c not in '\n\t' for c in text):
        raise ValueError('参考脚本包含不支持的控制字符。')
    return text


def load(data):
    path=data/'reference-script.json'
    value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return dict(enabled=bool(value.get('enabled',False)),text=validate(value.get('text','')))


def save(data,text,enabled):
    value=dict(enabled=bool(enabled),text=validate(text))
    write_json(data/'reference-script.json',value)
    return value


def context(terms,text=''):
    hints=vocabulary_context(terms)
    script=validate(text)
    if not script:return hints
    return ('请根据实际音频转写。以下是可能对应的参考脚本，用于理解语境、专名和用词。'
            '口播可能有增删、改词或顺序变化，请保留实际说出的内容，不补写未说出的脚本，不照抄脚本。\n'
            + ('参考词汇：'+hints+'\n' if hints else '')
            + '参考脚本（仅作参考）：\n'+script)
