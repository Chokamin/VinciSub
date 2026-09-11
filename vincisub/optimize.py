"""Deterministic subtitle cleanup. No wording or start-time changes."""
import math
import unicodedata
from .subtitles import validate_captions


def clean_text(text,ending=False,all_punctuation=False):
    if all_punctuation:
        result=''.join(c for c in text if not unicodedata.category(c).startswith('P')).strip()
    elif ending:
        # Preserve closing quotes/brackets while removing commas/periods inside them.
        closers='”’」』》〉】〕）)]}' + chr(34) + chr(39)
        index=len(text.rstrip());suffix=''
        while index:
            char=text[index-1]
            if char in closers:suffix=char+suffix
            elif char not in '，。,.．｡､ \n\r\t':break
            index-=1
        result=text[:index]+suffix
    else:
        result=text
    # A punctuation-only caption must not become an invalid empty subtitle.
    return result if result.strip() else text


def optimize(rows,ending=True,all_punctuation=False,fill_gaps=False,max_gap=.5):
    if not math.isfinite(max_gap) or not 0<=max_gap<=10:
        raise ValueError('间隙阈值应在 0–10 秒之间。')
    validate_captions(rows)
    result=[dict(row) for row in rows]
    for index,row in enumerate(result):
        row['text']=clean_text(row['text'],ending,all_punctuation)
        if fill_gaps and index+1<len(result):
            gap=result[index+1]['start']-row['end']
            if 0<gap<=max_gap+1e-9:
                row['end']=result[index+1]['start']
    validate_captions(result)
    return result
