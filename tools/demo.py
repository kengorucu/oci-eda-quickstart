#!/usr/bin/env python3
"""Prepare, run and inspect the E6 OKE demo using Python and kubectl."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from workloads import WORKLOADS

ROOT = Path(__file__).resolve().parents[1]
HOME_RESULTS = Path.home() / 'eda-e6-demo-results'
NAMESPACE = 'eda-native-poc'
JOB = WORKLOADS['rtl']['job']
DEMO = 'rtl'

def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')

def kubectl(args, payload=None, timeout=90):
    p = subprocess.run(['kubectl', *args], input=payload, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return p.stdout

def write_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)

def ready_nodes():
    data = json.loads(kubectl(['get', 'nodes', '-l',
        'node.kubernetes.io/instance-type=VM.Standard.E6.Flex,compute-family=e6,workload=eda-regression', '-o', 'json']))
    nodes = [n for n in data['items'] if not n['metadata'].get('deletionTimestamp') and
             any(c['type']=='Ready' and c['status']=='True' for c in n['status'].get('conditions', []))]
    if len(nodes) != 2:
        raise RuntimeError(f'Expected exactly two matching Ready E6 nodes; found {len(nodes)}. Check the cluster context and node pools.')
    return nodes

def prepare():
    ready_nodes()
    print(kubectl(['apply', '-f', str(ROOT/'benchmark'/f'{DEMO}-workers.json')]), end='')
    print('Preparing the selected workload and running a functional self-test inside both pods.')
    # Wait on the exact two Indexed Job pods rather than unrelated namespace pods.
    kubectl(['-n', NAMESPACE, 'wait', '--for=create', 'pod', '-l', f'poc-run={JOB}', '--timeout=120s'], timeout=150)
    print(kubectl(['-n', NAMESPACE, 'wait', '--for=condition=Ready', 'pod', '-l', f'poc-run={JOB}', '--timeout=900s'], timeout=930), end='')
    print(kubectl(['-n', NAMESPACE, 'get', 'pods', '-l', f'poc-run={JOB}', '-o', 'wide']), end='')
    print(f'Prepared. No timed benchmark has started. Run: python3 tools/demo.py run --demo {DEMO}')

def selected_session(argument=None):
    if argument:
        path = Path(argument).expanduser().resolve()
    else:
        latest = HOME_RESULTS/'latest.json'
        if not latest.exists():
            raise RuntimeError('No demo session found. Start one with: python3 tools/demo.py run')
        path = Path(json.loads(latest.read_text())['session'])
    if not (path/'status.json').is_file():
        raise RuntimeError(f'No session status file in {path}')
    return path

def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def start(detach=False):
    ready_nodes()
    pods = json.loads(kubectl(['-n', NAMESPACE, 'get', 'pods', '-l', f'poc-run={JOB}', '-o', 'json']))['items']
    if len(pods)!=2 or any(not any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions',[])) for p in pods):
        raise RuntimeError('Both demo pods must be Ready. Run prepare first.')
    HOME_RESULTS.mkdir(exist_ok=True)
    lock = HOME_RESULTS/'.active'
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError('A run lock exists. Inspect `python3 tools/demo.py watch`. Do not start overlapping measurements. If the session was interrupted, use unlock after checking its processes.')
    session = HOME_RESULTS / ('demo-'+stamp())
    try:
        session.mkdir()
        write_json(session/'status.json', {'state':'starting','started_utc':datetime.now(timezone.utc).isoformat(), 'workload_id':DEMO})
        write_json(HOME_RESULTS/'latest.json', {'session':str(session)})
        with (session/'controller.log').open('w') as log:
            child = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '_worker', '--demo', DEMO, '--session', str(session)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        write_json(lock/'owner.json', {'session':str(session),'pid':child.pid})
    except Exception:
        shutil.rmtree(lock)
        raise
    print(f'Background benchmark started. Session: {session}')
    print('Cloud Shell terminal disconnections do not restart this measurement. A Cloud Shell environment reset can still interrupt it.')
    if detach:
        print('Monitor live: python3 tools/demo.py watch')
        return 0
    return watch(session, process=child)

def worker(session):
    state = {'state':'running','pid':os.getpid(),'started_utc':datetime.now(timezone.utc).isoformat(), 'workload_id':DEMO}
    write_json(session/'status.json',state)
    code = 1
    try:
        code = subprocess.call([sys.executable, '-u', str(ROOT/'tools/run_scaling.py'), '--compute-family','e6', '--workload',DEMO, '--worker-job',JOB, '--output',str(session)])
        results = sorted(session.glob('*/comparison.json'))
        if code == 0 and len(results) == 1:
            state['state'] = 'complete'; state['result_directory'] = str(results[0].parent)
            shutil.copyfile(results[0], session/'comparison.json')
            print('COMPLETE. Export results with: python3 tools/demo.py export',flush=True)
        else:
            state['state'] = 'failed'; code = code or 1
            print('FAILED. Evidence retained. No automatic remeasurement.',flush=True)
    except Exception as exc:
        state.update(state='failed', error=str(exc))
        print(str(exc),flush=True)
    finally:
        state['exit_code'] = code; state['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(session/'status.json',state)
        lock=HOME_RESULTS/'.active'
        if lock.exists():
            owner=lock/'owner.json'
            if owner.exists() and json.loads(owner.read_text())['session']==str(session):
                shutil.rmtree(lock)
    return code

def watch(session, process=None, poll_interval=0.5):
    """Stream appended log text; never start, restart or terminate the worker."""
    print(f'Live progress: {session}', flush=True)
    print('Ctrl+C stops this view; the benchmark continues. Reconnect with: python3 tools/demo.py watch', flush=True)
    offset = 0
    previous = None
    try:
        while True:
            log = session/'controller.log'
            if log.exists():
                with log.open(errors='replace') as stream:
                    stream.seek(offset)
                    chunk = stream.read()
                    offset = stream.tell()
                if chunk:
                    print(chunk, end='', flush=True)
            state = json.loads((session/'status.json').read_text())
            if state['state'] != previous:
                print(f"\nState: {state['state']}", flush=True)
                previous = state['state']
            if state['state'] in ('complete', 'failed', 'interrupted'):
                # The state write is the completion boundary. Drain any last log
                # bytes appended between this loop's first read and that write.
                if log.exists():
                    with log.open(errors='replace') as stream:
                        stream.seek(offset)
                        print(stream.read(), end='', flush=True)
                return 0 if state['state']=='complete' else (state.get('exit_code') or 1)
            pid = state.get('pid')
            if not pid:
                owner=HOME_RESULTS/'.active/owner.json'
                if owner.exists():
                    record=json.loads(owner.read_text())
                    if record.get('session')==str(session):pid=record.get('pid')
            exited = process.poll() is not None if process is not None else (pid is not None and not alive(pid))
            if exited:
                # Recheck completion after observing process exit to avoid
                # confusing a final status update with an interrupted run.
                current=json.loads((session/'status.json').read_text())
                if current['state'] in ('complete','failed','interrupted'):
                    continue
                current.update(state='interrupted', error='Controller exited before recording completion.')
                write_json(session/'status.json', current)
                print('Controller interrupted. Evidence retained; no automatic restart.', flush=True)
                return 1
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print('\nLive view closed. The background benchmark was not stopped. Reattach with: python3 tools/demo.py watch', flush=True)
        return 0

def status(session):
    data=json.loads((session/'status.json').read_text())
    if data['state']=='running' and not alive(data['pid']):
        data['state']='interrupted'
    print(f'Session: {session}')
    print(json.dumps(data,indent=2))
    log=session/'controller.log'
    if log.exists():
        print('\nRecent progress:')
        print('\n'.join(log.read_text().splitlines()[-8:]))
    if (session/'comparison.json').exists():
        print('\nResults:')
        print((session/'comparison.json').read_text())

def export(session):
    data=json.loads((session/'status.json').read_text())
    if data['state']!='complete':
        raise RuntimeError('The run is not complete. Inspect status and retain existing evidence; no automatic restart.')
    archive=session.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as target:
        for p in sorted(session.rglob('*')):
            if p.is_symlink():
                raise RuntimeError('Unexpected symbolic link in result directory')
            if p.is_file() and not p.name.endswith('.tar.gz'):
                target.add(p,arcname=str(Path(session.name)/p.relative_to(session)),recursive=False)
    print(f'Download raw evidence: {archive}')
    print(f'Download chart input: {session}/comparison.json')
    print('Load comparison.json in the demo page to display your own results. Browser processing stays local.')

def cleanup():
    lock=HOME_RESULTS/'.active'
    if lock.exists():
        raise RuntimeError('A measurement is active or interrupted. Inspect status before removing workers.')
    print(kubectl(['-n',NAMESPACE,'delete','job',JOB,'--ignore-not-found']),end='')
    print(kubectl(['-n',NAMESPACE,'delete','configmap',JOB+'-files','--ignore-not-found']),end='')
    print('Benchmark workers removed. Local results and result ConfigMaps retained. Use Resource Manager Destroy to remove the cloud infrastructure after exporting results.')

def unlock():
    lock=HOME_RESULTS/'.active'
    owner=lock/'owner.json'
    if owner.exists():
        data=json.loads(owner.read_text())
        if alive(data['pid']):
            raise RuntimeError('Controller process still exists; lock retained. Do not run overlapping benchmarks.')
    if lock.exists():
        shutil.rmtree(lock)
    print('Stale lock removed. Existing measurements retained; no run restarted.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','run','watch','status','export','cleanup','unlock','_worker'])
    parser.add_argument('--session',help='Result session path; defaults to latest session')
    parser.add_argument('--demo', choices=list(WORKLOADS), default='rtl')
    parser.add_argument('--detach', action='store_true', help='Start without attaching the live view (run only)')
    args=parser.parse_args()
    global DEMO, JOB
    DEMO=args.demo; JOB=WORKLOADS[DEMO]['job']
    if args.command=='prepare': prepare()
    elif args.command=='run': return start(detach=args.detach)
    elif args.command=='watch': return watch(selected_session(args.session))
    elif args.command=='cleanup': cleanup()
    elif args.command=='unlock': unlock()
    elif args.command=='_worker': return worker(selected_session(args.session))
    elif args.command=='status': status(selected_session(args.session))
    else: export(selected_session(args.session))
    return 0

if __name__=='__main__':
    try:
        sys.exit(main())
    except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);sys.exit(1)
