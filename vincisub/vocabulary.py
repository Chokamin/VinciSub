"""Local recognition hints. Never rewrite a transcript by string replacement."""
import json
import re
from .storage import write_json


def parse(text):
    if not isinstance(text,str):
        raise ValueError('词库必须为文本。')
    terms=list(dict.fromkeys(t.strip() for t in re.split(r'[\n\r,，;；、]+',text) if t.strip()))
    if len(terms)>100 or sum(map(len,terms))>2000:
        raise ValueError('词库最多 100 个词、合计 2000 字，请保留本次音频相关词汇。')
    if any(len(t)>64 or any(ord(c)<32 for c in t) for t in terms):
        raise ValueError('每个词最多 64 字，不支持控制字符。')
    return terms


def load(data):
    path=data/'vocabulary.json'
    if not path.exists():
        return dict(enabled=True,terms=[])
    value=json.loads(path.read_text(encoding='utf-8'))
    return dict(enabled=bool(value.get('enabled',True)),terms=parse('\n'.join(value.get('terms',[]))))


def save(data,text,enabled=True):
    value=dict(enabled=bool(enabled),terms=parse(text))
    write_json(data/'vocabulary.json',value)
    return value


def context(terms):
    terms=parse('\n'.join(terms))
    return '，'.join(terms)
