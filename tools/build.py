#!/usr/bin/env python3
"""Build public demo downloads and a deployment link for GitHub Pages."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from manifests import build as build_manifests

ROOT=Path(__file__).resolve().parents[1]

def zip_files(target, paths):
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for file,relative in sorted(paths,key=lambda x:str(x[1])):
            info=ZipInfo(str(relative),date_time=(2026,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o100644 << 16
            z.writestr(info,file.read_bytes())

def build(repository='',release=''):
    if repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Repository must be owner/name')
    if release and not re.fullmatch(r'[A-Za-z0-9_.-]+',release):
        raise ValueError('Unsafe release tag')
    if bool(repository)!=bool(release):raise ValueError('Supply both repository and release, or neither')
    build_manifests()
    downloads=ROOT/'docs/downloads';downloads.mkdir(exist_ok=True)
    stack=[(p,p.name) for p in (ROOT/'stack').iterdir() if p.suffix=='.tf' or p.name in ('schema.yaml','README.md','.terraform.lock.hcl')]
    zip_files(downloads/'oke-e6-stack.zip',stack)
    operator=[]
    for folder in ('benchmark','tools'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.name not in ('build.py',):
                operator.append((p,Path('e6-oke-demo')/p.relative_to(ROOT)))
    operator.append((ROOT/'RUNBOOK.md',Path('e6-oke-demo/RUNBOOK.md')))
    zip_files(downloads/'oke-e6-benchmark.zip',operator)
    sums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(downloads.glob('*.zip'))}
    (downloads/'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name,sha in sums.items()))
    config={'repository':repository,'release':release,'stack_url':f'https://github.com/{repository}/releases/download/{release}/oke-e6-stack.zip' if repository else '', 'benchmark_url':f'https://github.com/{repository}/releases/download/{release}/oke-e6-benchmark.zip' if repository else '', 'checksums':sums}
    (ROOT/'docs/deployment.json').write_text(json.dumps(config,indent=2)+'\n')
    print('Built stack ZIP, benchmark ZIP, checksums and GitHub Pages configuration.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',default='');p.add_argument('--release',default='');a=p.parse_args();build(a.repository,a.release)
