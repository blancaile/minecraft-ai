"""Explicit live-Jev or dummy loopback faults on an isolated pinned Paper server.

No shared-server connection; .env is loaded only in --mode live. Never saves a key.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
SERVER_SHA = 'e708e8c132dc143ffd73528cccb9532e2eb17628b1a0eee74469bf466c7003f8'
CONFIG = dict(apiKey='env:JEV_API_KEY', model='jev-1.13.0', actionTicks=4,
              timeoutSeconds=10, maxObservationAgeTicks=200, maxDecisions=60,
              maxRunSeconds=120, observationRadius=3, goalRadius=1.0, maxDistanceFromSpawn=64.0)
PRESETS = [dict(name='south', yaw=0, goal=[.5,81,20.5]),
           dict(name='east-facing-south', yaw=0, goal=[20.5,81,.5]),
           dict(name='west-facing-north', yaw=180, goal=[-19.5,81,.5]),
           dict(name='obstacle', yaw=0, goal=[.5,81,20.5], obstacle=True)]

def save(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')

def events(path):
    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith('\n')]

def summarize(path):
    rows = events(path)
    meta = rows[0]['data']
    assert rows[0]['event'] == 'run_started'
    obs = {r['data']['observation_id']: r for r in rows if r['event'] == 'observation'}
    decisions = [r for r in rows if r['event'] == 'decision']
    inputs = {r['data']['request_id']: r for r in rows if r['event'] == 'input'}
    results = {r['data']['request_id']: r for r in rows if r['event'] == 'result'}
    ids=[r['data']['request_id'] for r in decisions]
    assert len(ids)==len(set(ids)) and set(ids)==set(inputs)==set(results)
    previous = None
    ages, latencies, counts, distances = [], [], [], []
    for d in decisions:
        rid = d['data']['request_id']
        o, i, r = obs[rid], inputs[rid], results[rid]
        choice = d['data']['response']['choice']
        assert choice in o['data']['legal_candidates']
        assert i['data']['source'] == 'JEV' and i['data']['action'] == r['data']['action'] == choice
        assert o['server_tick'] < d['server_tick'] == i['server_tick'] < r['server_tick']
        assert r['server_tick'] - i['server_tick'] == r['data']['actual_ticks'] == meta['config']['actionTicks']
        if previous:
            assert o['server_tick'] >= previous['server_tick']
            assert o['data']['previous'] == previous['data']
        previous = r
        age = d['server_tick'] - o['server_tick']
        assert age <= meta['config']['maxObservationAgeTicks']
        ages.append(age); latencies.append(d['data']['latency_ms'])
        counts.append(len(o['data']['legal_candidates']))
        before, after = i['data']['before'], r['data']['after']
        delta = [after['position'][j] - before['position'][j] for j in range(3)]
        assert all(abs(delta[j] - r['data']['displacement'][j]) < 1e-8 for j in range(3))
        turn = (after['yaw'] - before['yaw'] + 180) % 360 - 180
        assert abs(turn - {'TURN_LEFT':-15, 'TURN_RIGHT':15}.get(choice,0)) < .01
        distances.append(math.dist(before['position'], after['position']))
    terminal = rows[-1]['data']
    assert rows[-1]['event'] == 'terminal'
    if terminal['status'] == 'GOAL_REACHED':
        assert math.dist(terminal['final']['position'], meta['goal']) <= meta['config']['goalRadius']
    return dict(trace=path.name, artifact_sha256=meta['artifact_sha256'], fault_fixture=meta.get('fault_fixture',False),
                cycles=len(results), decisions=len(decisions), status=terminal['status'], reason=terminal['reason'],
                latency_ms=latencies, snapshot_age_ticks=ages, candidate_counts=counts,
                max_tick_gap_ms=terminal.get('max_tick_gap_ms'), path_length=sum(distances),
                actions=dict(Counter(d['data']['response']['choice'] for d in decisions)))

def obstacle_evidence(path, intervention):
    rows=events(path)
    snapshots=[r for r in rows if r['event']=='observation']
    before=[r for r in snapshots if r['server_tick']<=intervention['after_tick']]
    updated=[]
    for row in snapshots:
        if row['server_tick']<=intervention['after_tick']:continue
        if any(c.get('block')=='minecraft:stone' and -1<=c['position'][0]<=1 and 81<=c['position'][1]<=83
               and c['position'][2]==4 for c in row['data']['local_cells']):updated.append(row)
    assert before and updated, 'No observed wall update after fixture intervention'
    decisions={r['data']['request_id']:r['data']['response']['choice'] for r in rows if r['event']=='decision'}
    applied={r['data']['request_id']:r for r in rows if r['event']=='input'}
    after=[r for r in updated if r['data']['observation_id'] in decisions and r['data']['observation_id'] in applied]
    assert after, 'No Jev choice and execution tied to updated wall observation'
    prior=[decisions[r['data']['observation_id']] for r in before if r['data']['observation_id'] in decisions]
    subsequent=[decisions[r['data']['observation_id']] for r in after]
    changed=bool(prior and any(c!=prior[-1] for c in subsequent))
    reached=rows[-1]['data']['status']=='GOAL_REACHED'
    return dict(before_observation=before[-1]['data']['observation_id'],after_observations=[r['data']['observation_id'] for r in after],
                before_candidates=before[-1]['data']['legal_candidates'],after_candidates=[r['data']['legal_candidates'] for r in after],
                choices_before=prior,choices_after=subsequent,choice_changed=changed,
                adaptation='PASS' if changed and reached else 'FAILED',
                interpretation='Probe only: changed choice plus arrival, not a causal model-capability guarantee')

def aggregate(runs):
    latencies=sorted(v for run in runs for v in run['latency_ms'])
    return dict(runs=len(runs),cycles=sum(r['cycles'] for r in runs),
                terminals=dict(Counter(r['status'] for r in runs)),
                latency_p50_ms=statistics.median(latencies) if latencies else None,
                latency_p95_ms=latencies[math.ceil(len(latencies)*.95)-1] if latencies else None,
                max_snapshot_age_ticks=max((v for r in runs for v in r['snapshot_age_ticks']),default=None),
                max_tick_gap_ms=max((r['max_tick_gap_ms'] for r in runs if r['max_tick_gap_ms'] is not None),default=None))

def audit_directory(directory, shared=False):
    manifest=json.loads((directory/('live-experiment.json' if shared else 'verification.json')).read_text(encoding='utf-8'))
    if shared:
        assert manifest['status']=='GOAL_REACHED_PENDING_TRACE_VERIFICATION'
        assert manifest['config_restored'] and not manifest['cleanup_errors']
        trace=Path(manifest['terminal'].split(' trace=')[1]).name
        runs=[summarize(directory/trace)]
        assert len(runs)==1 and runs[0]['status']=='GOAL_REACHED' and runs[0]['cycles']>0 and not runs[0]['fault_fixture']
        assert runs[0]['artifact_sha256'] in manifest['receipts'][0]['receipt']['output'][0]
        assert any(r['command']=='jev despawn' and r['receipt']['success'] for r in manifest['receipts'])
    else:
        runs=[]
        for path in sorted((directory/'plugins/JevControl/traces').glob('*.jsonl')):
            if events(path)[0]['event']!='run_started':continue
            run=summarize(path)
            assert run['artifact_sha256']==manifest['artifact_sha256']
            intervention=directory/(path.stem+'-intervention.json')
            if intervention.exists():run['obstacle_evidence']=obstacle_evidence(path,json.loads(intervention.read_text(encoding='utf-8')))
            runs.append(run)
        if manifest['mode']=='live' and manifest['status']=='PASSED':
            assert len(runs)>=3 and sum(r['cycles'] for r in runs)>=100 and not any(r['fault_fixture'] for r in runs)
            assert any(r['status']=='GOAL_REACHED' for r in runs) and any('obstacle_evidence' in r for r in runs)
    audit=dict(status='PASSED' if shared else manifest['status'],runs=runs,aggregate=aggregate(runs))
    path=directory/('audit-'+uuid.uuid4().hex[:8]+'.json');save(path,audit)
    print(json.dumps(dict(path=str(path),status=audit['status'],aggregate=audit['aggregate'])))
    return audit

class Server:
    def __init__(self, root, artifact, environment, endpoint=None):
        self.root = root
        self.data = root/'plugins/JevControl'
        self.data.mkdir(parents=True)
        shutil.copy2(artifact, root/'plugins'/artifact.name)
        cached = REPO/'.runtime-harness/cache/paper-1.21.11-116.jar'
        assert hashlib.sha256(cached.read_bytes()).hexdigest() == SERVER_SHA
        shutil.copy2(cached, root/'server.jar')
        shutil.copy2(REPO/'harness/gate_a/fixtures/server-1.21.3-v1/payload/eula.txt', root/'eula.txt')
        (root/'server.properties').write_text('online-mode=false\nserver-ip=127.0.0.1\nserver-port='+('25581' if endpoint else '25580')+'\nenable-rcon=false\nmax-players=1\nview-distance=3\nsimulation-distance=3\nlevel-type=minecraft:flat\ngenerate-structures=false\nspawn-protection=0\nlevel-seed=314159\n',encoding='utf-8')
        save(self.data/'jev-control.json', CONFIG)
        command=['java','-Xms512M','-Xmx2G']
        if endpoint: command.append('-Djev.fixture.endpoint='+endpoint)
        command += ['-jar','server.jar','nogui']
        self.process=subprocess.Popen(command,cwd=root,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT,text=True,encoding='utf-8',bufsize=1)
        self.lines=queue.Queue()
        def read():
            with (root/'console.log').open('w',encoding='utf-8') as log:
                for line in self.process.stdout:
                    log.write(line);log.flush();self.lines.put(line)
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()

    def wait(self, text, seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if self.process.poll() is not None: raise RuntimeError('Isolated Paper exited during '+text)
            try: line=self.lines.get(timeout=.2)
            except queue.Empty: continue
            if text in line: return
        raise TimeoutError('Missing server event: '+text)

    def send(self, command):
        self.process.stdin.write(command+'\n');self.process.stdin.flush()

    def command(self, command):
        rid=str(uuid.uuid4());folder=self.data/'inbox'
        stage=folder/(rid+'.upload')
        save(stage,dict(id=rid,command=command,expires_at_ms=int(time.time()*1000)+10000))
        stage.rename(folder/(rid+'.json'))
        receipt=self.data/'receipts'/(rid+'.json')
        deadline=time.monotonic()+15
        while not receipt.exists() and time.monotonic()<deadline: time.sleep(.05)
        result=json.loads(receipt.read_text(encoding='utf-8'))
        assert result['success'], result
        return result

    def setup(self):
        self.wait('Done (',300)
        self.send('gamerule minecraft:spawn_mobs false')
        self.send('forceload add -64 -64 64 64')
        time.sleep(2)
        self.send('fill -63 80 -63 63 80 63 minecraft:stone');self.wait('Successfully filled')

    def prepare(self, preset, config):
        save(self.data/'jev-control.json',config)
        # Fixture geometry and initial pose only; no teleport after /jev start.
        for y in range(81,85):self.send(f'fill -63 {y} -63 63 {y} 63 minecraft:air')
        time.sleep(.4)
        self.command('jev spawn 0.5 81 0.5 world')
        self.send(f"execute as JevBot at @s run tp @s ~ ~ ~ {preset['yaw']} 0")
        time.sleep(.5)
        self.command('jev goal '+' '.join(map(str,preset['goal']))+' world')
        before=set((self.data/'traces').glob('*.jsonl')) if (self.data/'traces').exists() else set()
        self.command('jev start')
        added=set((self.data/'traces').glob('*.jsonl'))-before
        assert len(added)==1
        return added.pop()

    def release_check(self):
        time.sleep(1.3)
        reply=self.command('jev observe')
        name=Path(reply['output'][0].split('Observation written: ')[1]).name
        after=events(self.data/'traces'/name)[0]['data']['self']
        assert math.hypot(after['velocity'][0],after['velocity'][2]) < .001
        assert after['health'] > 0
        return after

    def close(self):
        if self.process.poll() is None:
            self.send('stop')
            try:self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=10)
        self.reader.join(timeout=5)

class Faults:
    def __init__(self):
        self.mode='api';self.count=0;self.second=threading.Event();self.attempted=threading.Event()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.headers['Authorization']=='Bearer fixture-only-no-credential'
                owner.count+=1
                if owner.count==2:
                    owner.second.set()
                    if owner.mode=='network':self.connection.close();return
                    if owner.mode=='api':self.send_response(503);self.end_headers();return
                    if owner.mode in ('stale','timeout','late'):time.sleep(2)
                choices=payload['questions']['next_action']['criteria']
                choice='UNKNOWN_ACTION' if owner.count==2 and owner.mode=='unknown' else 'FORWARD'
                data=dict(model=payload['model'],answers=dict(next_action=dict(choice=choice,confidence=1,
                          probabilities={c:1 if c=='FORWARD' else 0 for c in choices})))
                raw=json.dumps(data).encode()
                try:
                    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except ConnectionError:pass # Expected transport cancellation in timeout/late cases.
                finally:
                    if owner.count>=2:owner.attempted.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['live','faults'],required=True)
    parser.add_argument('--key-file',type=Path)
    parser.add_argument('--artifact',type=Path,default=REPO/'build/libs/jev-control-paper-0.2.0.jar')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    plan=dict(mode=args.mode,config={k:v for k,v in CONFIG.items() if k!='apiKey'},presets=PRESETS,
              max_episodes=8,min_cycles=100,obstacle='After >= 3 completed cycles, fixed wall x=-1..1 y=81..83 z=4',
              fault_cases=['api','network','unknown','stale','timeout','late'])
    plan['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    plan['tracked_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=REPO)).hexdigest()
    if not args.execute:print(json.dumps(plan,indent=2));return
    root=REPO/'.runtime-harness'/('paper-'+args.mode+'-'+uuid.uuid4().hex[:12]);root.mkdir(parents=True)
    save(root/'plan.json',plan);print('EVIDENCE_DIRECTORY='+str(root),flush=True)
    environment=os.environ.copy();environment.pop('JEV_API_KEY',None)
    if args.mode=='live':
        if not args.key_file:raise ValueError('--key-file is required for live mode')
        sys.path.insert(0,str(REPO/'tools/probes'))
        from jev_client import load_jev_api_key
        environment['JEV_API_KEY']=load_jev_api_key(args.key_file)
    fault=Faults() if args.mode=='faults' else None
    server=None;report=dict(status='RUNNING',runs=[],mode=args.mode,artifact_sha256=hashlib.sha256(args.artifact.read_bytes()).hexdigest())
    try:
        server=Server(root,args.artifact,environment,f'http://127.0.0.1:{fault.server.server_port}/' if fault else None)
        environment.pop('JEV_API_KEY',None)
        server.setup()
        cases=plan['fault_cases'] if fault else list(range(8))
        for case in cases:
            preset=PRESETS[case%4] if not fault else PRESETS[0]
            config=CONFIG.copy()
            if fault:
                fault.mode=case;fault.count=0;fault.second.clear();fault.attempted.clear()
                config['apiKey']='fixture-only-no-credential'
                if case=='stale':config['maxObservationAgeTicks']=5
                if case=='timeout':config['timeoutSeconds']=1
            path=server.prepare(preset,config)
            deadline=time.monotonic()+config['maxRunSeconds']+5
            intervention=None;cancelled=False
            while time.monotonic()<deadline:
                rows=events(path)
                if rows[-1]['event']=='terminal':break
                if fault and case=='late' and fault.second.is_set() and not cancelled:
                    server.command('jev stop');cancelled=True
                if not fault and preset.get('obstacle') and intervention is None and sum(r['event']=='result' for r in rows)>=3:
                    server.send('fill -1 81 4 1 83 4 minecraft:stone')
                    server.wait('Successfully filled')
                    intervention=dict(after_tick=rows[-1]['server_tick'],after_results=sum(r['event']=='result' for r in rows),wall=[[-1,81,4],[1,83,4]])
                    save(root/(path.stem+'-intervention.json'),intervention)
                time.sleep(.03)
            else:raise TimeoutError('Run exceeded declared wall budget')
            if fault and case=='late':
                assert cancelled and fault.attempted.wait(5)
                time.sleep(.5)
            result=summarize(path)
            result.update(preset=preset,intervention=intervention)
            report['runs'].append(result) # Preserve the run even if its postcondition check fails.
            if intervention:result['obstacle_evidence']=obstacle_evidence(path,intervention)
            result['settled']=server.release_check()
            if fault:
                result['fault']=case;result['requests']=fault.count
                assert result['status']==('CANCELLED' if case=='late' else 'ERROR')
                assert result['cycles']==1 and fault.count==2
                expected={'api':'Jev HTTP 503','unknown':'Invalid Jev response','stale':'Stale observation','late':'Operator stopped run'}
                if case in expected:assert expected[case] in result['reason']
                # Run the same goal-requiring verifier as a real failing runner process.
                check=subprocess.run([sys.executable,str(Path(__file__)), '--verify-trace',str(path)],capture_output=True,text=True)
                result['runner_exit_code']=check.returncode
                assert check.returncode==1
            elif result['status']=='ERROR':
                raise RuntimeError('Live API run stopped with ERROR; no automatic retry')
            report['aggregate']=aggregate(report['runs']);save(root/'verification.json',report)
            print(json.dumps({k:result[k] for k in ('trace','cycles','status','actions')}),flush=True)
            server.command('jev despawn')
            if not fault and case>=3 and sum(r['cycles'] for r in report['runs'])>=100:break
        if not fault:
            assert len(report['runs'])>=3 and sum(r['cycles'] for r in report['runs'])>=100
            assert any(r['status']=='GOAL_REACHED' for r in report['runs'])
            assert any(r['intervention'] for r in report['runs'])
        report['status']='PASSED'
    except BaseException as exc:
        report['status']='FAILED';report['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        if server:server.close()
        if fault:fault.server.shutdown();fault.server.server_close()
        save(root/'verification.json',report)
        print('STATUS='+report['status'],flush=True)

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1] in ('--audit-directory','--verify-shared'):
        audit_directory(Path(sys.argv[2]),shared=sys.argv[1]=='--verify-shared');sys.exit(0)
    if len(sys.argv)==3 and sys.argv[1]=='--verify-trace':
        try:sys.exit(0 if summarize(Path(sys.argv[2]))['status']=='GOAL_REACHED' else 1)
        except Exception:sys.exit(2)
    main()
