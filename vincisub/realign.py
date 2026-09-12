"""Re-align existing words locally; preserve uncertain timings for manual review."""
import json
import math
from pathlib import Path
from .storage import write_json
from .subtitles import validate_captions, Word, make_captions, aligned_text_words, bridge_brief_gaps
from dataclasses import asdict


def aligned_bounds(tokens,left,right,original):
    if not tokens:raise ValueError('没有对齐词语')
    previous=0
    for token in tokens:
        a,b=float(token.start_time),float(token.end_time)
        if not all(math.isfinite(t) for t in (a,b)) or a<previous-.001 or b<a or b>right-left+.001:
            raise ValueError('词语时间戳不可靠')
        previous=b
    start=left+float(tokens[0].start_time);end=left+float(tokens[-1].end_time)
    if end<=start:raise ValueError('整句时间戳不可靠')
    if abs(start-original['start'])>1 or abs(end-original['end'])>1:
        raise ValueError('偏移超出搜索范围')
    return start,end


def reconcile(original,proposed,failed,tail,duration,fps):
    if not math.isfinite(tail) or not 0<=tail<=1:raise ValueError('句尾保留时间应在 0–1 秒之间。')
    rows=[dict(r) for r in proposed];failed=set(failed)
    for i,row in enumerate(rows):
        if i not in failed:
            row['start']=max(0,math.floor(row['start']*fps)/fps)
            row['end']=min(duration,math.ceil(row['end']*fps)/fps)
    # Reject conflicting proposals, including conflicts with unchanged captions.
    while True:
        conflicts=set()
        for i in range(len(rows)-1):
            if rows[i]['end']>rows[i+1]['start']:
                conflicts.update((i,i+1))
        new=conflicts-failed
        if not new:break
        failed.update(new)
        for i in failed:rows[i]=dict(original[i])
    for i,row in enumerate(rows):
        if i in failed:continue
        limit=rows[i+1]['start'] if i+1<len(rows) else duration
        row['end']=min(limit,math.ceil((row['end']+tail)*fps)/fps)
    validate_captions(rows)
    return rows,sorted(failed)


def split_aligned(row, words, max_chars, fps, protected_terms=()):
    """Split using measured word boundaries; preserve the caption's outer span."""
    captions = bridge_brief_gaps(make_captions(words, max_chars=max_chars, protected_terms=protected_terms))
    if len(captions) <= 1:
        return [dict(row)]
    result = [asdict(c) for c in captions]
    for part in result:
        part['start'] = max(row['start'], round(part['start']*fps)/fps)
        part['end'] = min(row['end'], round(part['end']*fps)/fps)
    result[0]['start'] = row['start']
    result[-1]['end'] = row['end']
    validate_captions(result)
    normalize = lambda text: ''.join(text.split())
    if normalize(''.join(c['text'] for c in result)) != normalize(row['text']):
        raise ValueError('重新断句不能丢失或改变字幕文字')
    return result


def run(directory):
    from .models import cache_lock,ensure,ALIGNER,MODELS
    from .reference import context
    from .timeline import decode
    import numpy as np
    import torch
    from qwen_asr import Qwen3ForcedAligner,Qwen3ASRModel
    from opencc import OpenCC
    req=json.loads((directory/'request.json').read_text(encoding='utf-8'))
    def report(value):write_json(directory/'status.json',value)
    with cache_lock():
        model_path=ensure(ALIGNER,report)
        device='mps' if torch.backends.mps.is_available() else 'cpu'
        report(dict(state='running',message='正在加载时间对齐模型…'))
        script=req.get('reference_script','')
        if script:
            asr_path=ensure(MODELS['qwen-0.6b'],report)
            model=Qwen3ASRModel.from_pretrained(asr_path,dtype=torch.float32,device_map=device,attn_implementation='eager',max_inference_batch_size=1,max_new_tokens=512,forced_aligner=model_path,forced_aligner_kwargs=dict(dtype=torch.float32,device_map=device,attn_implementation='eager'))
        else:
            model=Qwen3ForcedAligner.from_pretrained(model_path,dtype=torch.float32,device_map=device,attn_implementation='eager')
        converter=OpenCC('t2s')
        audio,rate=decode(req['timeline'])
        origin=req['timeline']['offset'];duration=origin+req['timeline']['duration']
        rows=req['rows'];proposed=[dict(r) for r in rows];failed=[];measured={}
        for i,row in enumerate(rows):
            report(dict(state='running',message=f'正在对齐音频：{i+1} / {len(rows)}'))
            left=max(origin,row['start']-1);right=min(duration,row['end']+1)
            if script or req.get('resegment'):
                # Avoid transcribing neighbouring captions into this one.
                if i:left=max(left,(rows[i-1]['end']+row['start'])/2)
                if i+1<len(rows):right=min(right,(row['end']+rows[i+1]['start'])/2)
            segment=audio[round((left-origin)*rate):round((right-origin)*rate)]
            if right-left>30 or not len(segment) or np.max(np.abs(segment))<.0001:
                failed.append(i);continue
            try:
                text=row['text']
                if script:
                    results=model.transcribe(audio=(segment,rate),context=context(req.get('vocabulary',[]),script),language='Chinese',return_time_stamps=True)
                    text=converter.convert(''.join(r.text for r in results)).strip()
                    tokens=[t for r in results for t in (r.time_stamps or [])]
                    if not text:raise ValueError('未识别到文字')
                else:
                    tokens=model.align(audio=(segment,rate),text=row['text'],language='Chinese')[0].items
                start,end=aligned_bounds(tokens,left,right,row)
                if req.get('resegment'):
                    measured[i]=[Word(w.text,w.start+left,w.end+left) for w in aligned_text_words(tokens,text)]
                proposed[i]['text']=text
                if req.get('realign',True):proposed[i].update(start=start,end=end)
            except (ValueError,IndexError) as error:
                print(f'Alignment skipped {i+1}: {error}',flush=True)
                failed.append(i)
        if req.get('realign',True):
            result,failed=reconcile(rows,proposed,failed,req['tail'],duration,req['timeline']['fps'])
        else:
            result=proposed
            validate_captions(result)
        if req.get('resegment'):
            expanded=[];expanded_failed=[]
            for i,row in enumerate(result):
                if i in failed or i not in measured:
                    expanded_failed.append(len(expanded));expanded.append(dict(row));continue
                try:
                    parts=split_aligned(row,measured[i],req.get('max_chars',20),req['timeline']['fps'],req.get('vocabulary', []))
                except ValueError as error:
                    print(f'Resegmentation skipped {i+1}: {error}',flush=True)
                    expanded_failed.append(len(expanded));parts=[dict(row)]
                expanded.extend(parts)
            result=expanded;failed=expanded_failed
            validate_captions(result)
        write_json(directory/'result.json',dict(rows=result,failed=failed))
        report(dict(state='done',message=f'对齐完成，{len(failed)} 条保留原时间、需人工校对。'))


if __name__=='__main__':
    import sys
    directory=Path(sys.argv[1])
    try:run(directory)
    except Exception as error:
        write_json(directory/'status.json',dict(state='error',message=str(error)))
        raise
