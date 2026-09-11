"""Managed model cache, guarded deletion, and byte-based download reporting."""
import argparse
from contextlib import contextmanager
import fcntl
import fnmatch
import json
import os
from pathlib import Path
import shutil
import threading

from .storage import DATA, write_json

MODELS = {'qwen-0.6b':'Qwen/Qwen3-ASR-0.6B','qwen-1.7b':'Qwen/Qwen3-ASR-1.7B'}
ALIGNER = 'Qwen/Qwen3-ForcedAligner-0.6B'
REPOS = list(MODELS.values())+[ALIGNER]
LABELS = ['Qwen3-ASR 0.6B · 轻量','Qwen3-ASR 1.7B · 标准','ForcedAligner 0.6B · 共用时间对齐']
PATTERNS = ['*.json','*.safetensors','*.txt','*.model','*.tiktoken']


def cache_root(data=DATA):
    return Path(data)/'models'/'hub'


def repo_path(repo,data=DATA):
    if repo not in REPOS:
        raise ValueError('未知模型。')
    return cache_root(data)/('models--'+repo.replace('/','--'))


@contextmanager
def cache_lock(data=DATA,exclusive=False):
    root=Path(data)/'models';root.mkdir(parents=True,exist_ok=True)
    with (root/'vincisub.lock').open('a') as stream:
        try:
            fcntl.flock(stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('模型正在下载、识别或删除，请稍后再试。') from None
        try:
            yield
        finally:
            fcntl.flock(stream,fcntl.LOCK_UN)


def local_snapshot(repo,data=DATA):
    path=repo_path(repo,data)
    try:
        revision=(path/'refs'/'main').read_text(encoding='utf-8').strip()
        if not revision or '/' in revision or revision in ('.','..'):
            return None
        snapshot=path/'snapshots'/revision
        required=['config.json','tokenizer_config.json','preprocessor_config.json','vocab.json','merges.txt']
        index=snapshot/'model.safetensors.index.json'
        if index.is_file():
            required+=list(set(json.loads(index.read_text(encoding='utf-8'))['weight_map'].values()))
        else:
            required+=['model.safetensors']
        if all((snapshot/f).is_file() and (snapshot/f).stat().st_size>0 for f in required):
            return snapshot
    except (OSError,ValueError,KeyError):
        pass
    return None


def disk_bytes(path):
    total=0
    for root,dirs,files in os.walk(path,followlinks=False):
        for name in files:
            file=Path(root)/name
            if not file.is_symlink():
                try: total+=file.stat().st_size
                except FileNotFoundError: pass
    return total


def size_label(size):
    return f'{size/1024**3:.2f} GB' if size>=1024**3 else f'{size/1024**2:.1f} MB'


def inventory(data=DATA):
    return [dict(repo=repo,name=label,path=str(repo_path(repo,data).absolute()),bytes=disk_bytes(repo_path(repo,data)),
                 state='已下载' if local_snapshot(repo,data) else '下载未完成' if repo_path(repo,data).exists() else '未下载')
            for repo,label in zip(REPOS,LABELS)]


def delete(repo,data=DATA):
    path=repo_path(repo,data)
    with cache_lock(data,exclusive=True):
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
            raise ValueError('模型目录为符号链接，已停止删除。')
        if path.exists():
            shutil.rmtree(path)


def ensure(repo,report,data=DATA):
    """Caller holds a shared cache lock until model usage has finished."""
    snapshot=local_snapshot(repo,data)
    if snapshot:
        return str(snapshot)
    from huggingface_hub import HfApi,hf_hub_download
    report(dict(state='running',phase='download',message='正在查询模型文件…',model=repo,downloaded=0,total=0,progress=0))
    info=HfApi().model_info(repo,files_metadata=True)
    files=[f for f in info.siblings if any(fnmatch.fnmatch(f.rfilename,p) for p in PATTERNS)]
    total=sum(f.size or 0 for f in files)
    root=repo_path(repo,data)
    stop=threading.Event()
    def emit(done=False):
        downloaded=0
        for f in files:
            target=root/'snapshots'/info.sha/f.rfilename
            if target.is_file():
                downloaded+=min(target.stat().st_size,f.size or 0)
            else:
                lfs=f.lfs
                digest=(lfs.get('sha256') if isinstance(lfs,dict) else getattr(lfs,'sha256',None)) if lfs else f.blob_id
                partial=root/'blobs'/f'{digest}.incomplete'
                try: downloaded+=min(partial.stat().st_size,f.size or 0)
                except FileNotFoundError: pass
        report(dict(state='running',phase='download',message='下载完成，准备加载…' if done else '模型搬运中…',
                    model=repo,downloaded=downloaded,total=total,progress=100 if done else min(99,round(100*downloaded/total)) if total else 0))
    def monitor():
        while not stop.wait(.25):
            emit()
    emit()
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        for file in files:
            hf_hub_download(repo,file.rfilename,revision=info.sha,cache_dir=str(cache_root(data)))
        (root/'refs').mkdir(parents=True,exist_ok=True)
        (root/'refs'/'main').write_text(info.sha,encoding='utf-8')
    finally:
        stop.set();thread.join()
    snapshot=local_snapshot(repo,data)
    if snapshot is None:
        raise RuntimeError('模型文件不完整，请重新下载。')
    emit(True)
    return str(snapshot)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('repo',choices=REPOS);parser.add_argument('status',type=Path)
    args=parser.parse_args()
    latest={}
    def report(value):
        latest.update(value)
        write_json(args.status,value)
    try:
        with cache_lock():
            ensure(args.repo,report)
        write_json(args.status,dict(latest,state='done',message='模型已准备好。',progress=100))
    except Exception as error:
        write_json(args.status,dict(state='error',message=str(error),progress=0))
        raise SystemExit(1)


if __name__=='__main__': main()
