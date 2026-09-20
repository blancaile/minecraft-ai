"""Issue 40: isolated, bounded direct/assisted comparison. No live call without --execute.

Mock smoke uses only a loopback dummy policy and is never model acceptance evidence.
Final evaluation requires a successfully audited diagnostic with the same artifact.
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
import shutil
import subprocess
import threading
import time
import uuid
from jsonschema import Draft202012Validator

from paper_acceptance import Server, events as live_events
from p1_acceptance import CONFIG, PRESETS, REPO, SERVER_SHA256, _json, _sha256, events, EvidenceError

DIAGNOSTICS = {f'{side}-yaw-{yaw}': {'yaw': yaw, 'goal': [x,81,.5]}
               for side,x in [('west',-2.5),('east',3.5)] for yaw in (0,90)}
CONTRACT = dict(segment_length=.8, max_distance=1, max_ticks=12, wait_ticks=4,
                endpoint_tolerance=.12, stall_ticks=3, stall_distance=.01,
                max_input_ticks=240, max_decisions=60, max_seconds=120,
                guard='Observed full body footprint plus flat full-block support; UNKNOWN stops; no route selection',
                merge='Coordinates within 1e-9 blocks only; fixed E,SE,S,SW,W,NW,N,NE,GOAL_DIRECTION,WAIT order',
                wall_trigger='First server tick with actual z>=2.5; valid only if body front z<4')
SEGMENT_SCHEMA=json.loads((REPO/'docs/schemas/jev-segment-v1.schema.json').read_text(encoding='utf-8'))
SEGMENT_VALIDATOR=Draft202012Validator(SEGMENT_SCHEMA)


def schedule(phase, development_cases=None):
    if phase=='development':
        if not development_cases or len(development_cases)>6 or len(set(development_cases))!=len(development_cases):
            raise ValueError('Development requires one to six distinct predeclared cases')
        presets=DIAGNOSTICS|PRESETS
        return [dict(condition=name,mode='assisted',repeat=1,**presets[name]) for name in development_cases]
    if phase == 'diagnostic':
        return [dict(condition=name,mode=mode,repeat=1,**preset)
                for i,(name,preset) in enumerate(DIAGNOSTICS.items())
                for mode in (('direct','assisted') if i%2==0 else ('assisted','direct'))]
    if phase == 'final':
        return [dict(condition=name,mode=mode,repeat=repeat,**preset)
                for repeat in range(1,4) for i,(name,preset) in enumerate(PRESETS.items())
                for mode in (('direct','assisted') if (repeat+i)%2 else ('assisted','direct'))]
    raise ValueError('unknown phase')


def summarize(path):
    rows=events(path)
    for row in rows:
        if row['event'].startswith('segment_'):
            errors=list(SEGMENT_VALIDATOR.iter_errors(row))
            if errors: raise EvidenceError('Segment schema violation')
    if rows[0]['event']!='run_started' or rows[-1]['event']!='terminal': raise EvidenceError('Incomplete run')
    if sum(r['event']=='terminal' for r in rows)!=1: raise EvidenceError('Duplicate terminal')
    meta,terminal=rows[0]['data'],rows[-1]['data']; mode=meta['execution_mode']
    def index(kind,key):
        selected=[r for r in rows if r['event']==kind]
        result={r['data'][key]:r for r in selected}
        if len(selected)!=len(result): raise EvidenceError('Duplicate identifiers')
        return result
    obs=index('observation','observation_id'); decisions=index('decision','request_id')
    starts=index('segment_start' if mode=='assisted' else 'input','request_id')
    results=index('segment_result' if mode=='assisted' else 'result','request_id')
    if not set(decisions).issubset(obs) or set(decisions)!=set(starts) or set(starts)!=set(results):
        raise EvidenceError('Decision/start/result chain mismatch')
    if len(obs)-len(decisions)>1: raise EvidenceError('Multiple outstanding decisions')
    applied_ticks=[e for e in rows if e['event']==('segment_tick' if mode=='assisted' else 'direct_tick')]
    if any(e['data']['request_id'] not in starts for e in applied_ticks): raise EvidenceError('Unbound input tick')
    previous=None; total=0; cycles=[]; all_ids=set();recent=[]
    for rid,decision in decisions.items():
        o,s,r=obs[rid],starts[rid],results[rid]; choice=decision['data']['response']['choice']
        if o['data'].get('schema_version')=='jev-assisted-v2' and o['data'].get('recent_segments')!=recent[-4:]:
            raise EvidenceError('History differs from the last four measured segment results')
        if choice not in o['data']['legal_candidates']: raise EvidenceError('Choice not offered')
        if not o['server_tick']<decision['server_tick']==s['server_tick']<=r['server_tick']: raise EvidenceError('Tick order')
        if decision['server_tick']-o['server_tick']>meta['config']['maxObservationAgeTicks']: raise EvidenceError('Stale applied')
        if previous is not None and (o['data']['previous']!=previous['data'] or o['server_tick']<previous['server_tick']):
            raise EvidenceError('Previous result not bound')
        previous=r
        recent.append(r['data'])
        actual=(r['data']['after']['body_tick']-s['data']['before']['body_tick']) if mode=='assisted' else r['server_tick']-s['server_tick']
        total+=actual
        if actual!=r['data']['actual_ticks']: raise EvidenceError('Duration mismatch')
        before=s['data']['before']['position']; after=r['data']['after']['position']
        if any(abs(after[j]-before[j]-r['data']['displacement'][j])>1e-8 for j in range(3)): raise EvidenceError('Displacement mismatch')
        if mode=='assisted':
            selected=s['data']['selected']; sid=s['data']['segment_id']; endpoint=selected['endpoint']
            if sid in all_ids: raise EvidenceError('Reused segment')
            all_ids.add(sid)
            offered=[p for p in o['data']['point_candidates'] if p['id']==choice]
            if len(offered)!=1 or {k:v for k,v in offered[0].items() if k!='observed_sweep'}!=selected:
                raise EvidenceError('Selected destination changed')
            if r['data']['selected']!=selected or r['data']['segment_id']!=sid: raise EvidenceError('Result destination changed')
            if math.hypot(endpoint[0]-before[0],endpoint[2]-before[2])>1.000000001: raise EvidenceError('Unbounded endpoint')
            if not 0<=actual<=s['data']['max_ticks']<= (4 if choice=='WAIT' else 12): raise EvidenceError('Unbounded duration')
            ticks=[e for e in rows if e['event']=='segment_tick' and e['data']['segment_id']==sid]
            start_body=s['data']['before']['body_tick']
            if [e['data']['before']['body_tick'] for e in ticks]!=list(range(start_body,start_body+actual)): raise EvidenceError('Missing/duplicate input tick')
            measured_path=0; last=before
            for e in ticks:
                d=e['data']; p=d['before']['position']; measured_path+=math.hypot(p[0]-last[0],p[2]-last[2]);last=p
                if d['selected']!=selected or d['request_id']!=rid or d['strafe']!=0 or d['jump'] or not 0<=d['forward']<=1:
                    raise EvidenceError('Input substituted destination or primitive')
                if choice!='WAIT':
                    yaw=math.degrees(math.atan2(-(endpoint[0]-p[0]),endpoint[2]-p[2]))
                    if abs((d['yaw']-yaw+180)%360-180)>1e-4: raise EvidenceError('Yaw differs from endpoint geometry')
                    expected_forward=min(1,math.hypot(endpoint[0]-p[0],endpoint[2]-p[2])*2)
                    if abs(d['forward']-expected_forward)>1e-6: raise EvidenceError('Input strength differs from fixed geometry')
                elif d['forward']!=0: raise EvidenceError('WAIT moved')
            measured_path+=math.hypot(after[0]-last[0],after[2]-last[2])
            if measured_path>1.000001 or abs(measured_path-r['data']['path_length'])>1e-6: raise EvidenceError('Segment path limit or measurement mismatch')
        else:
            if choice!=s['data']['action'] or choice!=r['data']['action'] or actual!=meta['config']['actionTicks']:
                raise EvidenceError('Direct input changed')
            ticks=[e for e in rows if e['event']=='direct_tick' and e['data']['request_id']==rid]
            if [e['server_tick'] for e in ticks]!=list(range(s['server_tick'],r['server_tick'])): raise EvidenceError('Missing direct tick')
        cycles.append(dict(request_id=rid,choice=choice,ticks=actual,goal_distance=math.dist(after,meta['goal']),
                           latency_ms=decision['data']['latency_ms'],reason=r['data'].get('reason',r['data'].get('outcome'))))
    if total!=terminal['input_ticks'] or total>240 or len(decisions)>60 or terminal['decisions']!=len(decisions):
        raise EvidenceError('Common budget mismatch')
    final_distance=math.dist(terminal['final']['position'],meta['goal'])
    arrival=terminal['status']=='GOAL_REACHED'
    if arrival and (final_distance>meta['config']['goalRadius'] or terminal['elapsed_ms']>120000): raise EvidenceError('False arrival')
    if previous is not None:
        gap=rows[-1]['server_tick']-previous['server_tick']; last=previous['data']['after']
        if gap<0: raise EvidenceError('Terminal precedes actual result')
        final=terminal['final']['position']
        for axis in (0,2):
            drift=final[axis]-last['position'][axis]; velocity=last['velocity'][axis]
            bound=abs(velocity)*(1-.91**gap)/(1-.91)+1e-6
            if abs(drift)>bound or abs(drift)>1e-6 and drift*velocity<0: raise EvidenceError('Terminal position contradicts released motion')
    interventions=[e for e in rows if e['event']=='fixture_intervention']
    wall_chain=[]
    if len(interventions)==1:
        intervention=interventions[0]; low,high=intervention['data']['wall']
        if intervention['data']['valid_before_wall'] and 2.5<=intervention['data']['self']['position'][2]<3.7:
            for rid,o in obs.items():
                if rid not in results or o['server_tick']<intervention['server_tick']: continue
                if any(c.get('knowledge')=='OBSERVED' and c.get('block')=='minecraft:stone'
                       and all(low[j]<=c['position'][j]<=high[j] for j in range(3)) for c in o['data']['local_cells']): wall_chain.append(rid)
    return dict(run_id=meta['run_id'],mode=mode,artifact_sha256=meta['artifact_sha256'],config=meta['config'],
                fault_fixture=meta['fault_fixture'],spawn=meta['spawn'],goal=meta['goal'],
                initial=next(iter(obs.values()))['data']['self'] if obs else None,
                status=terminal['status'],arrival=arrival,final_distance=final_distance,
                input_ticks=total,decisions=len(decisions),elapsed_ms=terminal['elapsed_ms'],
                wall_chain=wall_chain,cycles=cycles,trace_sha256=_sha256(path))


def prepare(server,spec,config):
    _json(server.data/'jev-control.json',config)
    for y in range(81,85): server.send(f'fill -63 {y} -63 63 {y} 63 minecraft:air')
    time.sleep(.4)
    server.command('jev fixture-wall '+(spec['condition'] if 'wall' in spec else 'off'))
    server.command('jev spawn 0.5 81 0.5 world')
    server.send(f"execute as JevBot at @s run tp @s ~ ~ ~ {spec['yaw']} 0")
    time.sleep(.5)
    if spec.get('effect'): server.send(spec['effect']); time.sleep(.1)
    if spec.get('static_block'):
        server.send('fill 1 81 -1 1 83 1 minecraft:stone');server.wait('Successfully filled');time.sleep(.1)
    server.command('jev goal '+' '.join(map(str,spec['goal']))+' world')
    before=set((server.data/'traces').glob('*.jsonl')) if (server.data/'traces').exists() else set()
    server.command('jev start '+spec['mode'])
    added=set((server.data/'traces').glob('*.jsonl'))-before
    if len(added)!=1: raise EvidenceError('Missing unique run trace')
    return added.pop()


def wait_terminal(server,trace,cancel=False,late=False):
    deadline=time.monotonic()+125; cancelled=False
    while time.monotonic()<deadline:
        rows=live_events(trace)
        if rows and rows[-1]['event']=='terminal': return
        if cancel and not cancelled and any(e['event']=='segment_tick' for e in rows):
            server.send('jev stop');cancelled=True
        if late and not cancelled and sum(e['event']=='observation' for e in rows)>=2:
            time.sleep(.2);server.send('jev stop');cancelled=True
        time.sleep(.015)
    raise TimeoutError('Run did not stop within wall budget')


class Mock:
    """Deterministic wiring fixture, never a production or fallback policy."""
    def __init__(self):
        self.choice='E'; self.fault=None; self.requests=0
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.headers['Authorization']=='Bearer fixture-only-no-credential'
                owner.requests+=1
                active=owner.requests>=2
                if active and owner.fault=='api': self.send_response(503);self.end_headers();return
                if active and owner.fault=='network': self.connection.close();return
                if active and owner.fault in ('timeout','stale','late'): time.sleep(2)
                choices=payload['questions']['next_action']['criteria']
                choice='BOGUS' if active and owner.fault=='unknown' else owner.choice
                raw=json.dumps(dict(model=payload['model'],answers=dict(next_action=dict(choice=choice,confidence=1,
                    probabilities={c:1 if c==owner.choice else 0 for c in choices})))).encode()
                try:
                    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except ConnectionError: pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()


def verdict(runs,phase,development_cases=None):
    expected=schedule(phase,development_cases)
    if len(runs)!=len(expected) or any((r['condition'],r['mode'],r['repeat'])!=(s['condition'],s['mode'],s['repeat']) for r,s in zip(runs,expected)):
        return False
    if any(r.get('fault_fixture') or not r.get('valid_trace') or not r.get('settled') for r in runs): return False
    if phase=='diagnostic': return all(r['arrival'] for r in runs if r['mode']=='assisted')
    if phase=='development': return all(r['arrival'] and (r['condition'] not in PRESETS or bool(r['wall_chain'])) for r in runs)
    return all(sum(r['arrival'] and bool(r['wall_chain']) for r in runs if r['mode']=='assisted' and r['condition']==c)>=2 for c in PRESETS) and all(r['wall_chain'] for r in runs)


def audit(root):
    plan=json.loads((root/'plan.json').read_text(encoding='utf-8')); report=json.loads((root/'verification.json').read_text(encoding='utf-8'))
    if report['plan_sha256']!=_sha256(root/'plan.json') or plan['contract']!=CONTRACT: raise EvidenceError('Plan binding')
    for filename,digest in plan['evaluator_files'].items():
        if _sha256(root/filename)!=digest: raise EvidenceError('Evaluator snapshot binding')
    if plan['schedule']!=schedule(plan['phase'],plan.get('development_cases')): raise EvidenceError('Schedule differs from predeclared conditions')
    if _sha256(root/'plugins'/plan['artifact_filename'])!=plan['artifact_sha256']: raise EvidenceError('Artifact binding')
    raw={p.name for p in (root/'plugins/JevControl/traces').glob('*.jsonl') if events(p)[0]['event']=='run_started'}
    if raw!={r['trace'] for r in report['runs']}: raise EvidenceError('Unreported raw runs')
    for r,spec in zip(report['runs'],plan['schedule']):
        actual=summarize(root/'plugins/JevControl/traces'/r['trace'])
        if any(r.get(k)!=v for k,v in actual.items()): raise EvidenceError('Raw result differs from report')
        if actual['artifact_sha256']!=plan['artifact_sha256'] or actual['goal']!=spec['goal'] or actual['spawn']!=[.5,81,.5] or actual['mode']!=spec['mode']:
            raise EvidenceError('Run differs from plan')
        if actual['config']!={k:v for k,v in CONFIG.items() if k!='apiKey'}: raise EvidenceError('Config differs from fixed budget')
        if math.dist(actual['initial']['position'],[.5,81,.5])>.01 or abs((actual['initial']['yaw']-spec['yaw']+180)%360-180)>.01: raise EvidenceError('Initial pose differs')
        receipt=r['despawn_receipt']
        raw_receipt=json.loads((root/'plugins/JevControl/receipts'/(receipt['id']+'.json')).read_text(encoding='utf-8'))
        if receipt!=raw_receipt or not receipt['success']: raise EvidenceError('Cleanup receipt invalid')
        settled=r['settled']; observed=root/'plugins/JevControl/traces'/r['settled_trace']
        if events(observed)[0]['data']['self']!=settled or math.hypot(*[settled['velocity'][i] for i in (0,2)])>=.001 or settled['health']<=0:
            raise EvidenceError('Settled physical observation invalid')
    cleanup=report['cleanup']; receipt=cleanup['receipt']
    if receipt!=json.loads((root/'plugins/JevControl/receipts'/(receipt['id']+'.json')).read_text(encoding='utf-8')) or not receipt['success'] or not any('bot=none' in line for line in receipt['output']): raise EvidenceError('Final cleanup missing')
    passed=verdict(report['runs'],plan['phase'],plan.get('development_cases'))
    return dict(passed=passed,phase=plan['phase'],artifact_sha256=plan['artifact_sha256'],runs=len(report['runs']))


def execute(args,plan):
    mock=Mock() if args.phase=='smoke' else None
    root=REPO/'.runtime-harness'/('p1b-'+args.phase+'-'+uuid.uuid4().hex[:12]);root.mkdir(parents=True)
    _json(root/'plan.json',plan)
    for name in ('p1b_acceptance.py','paper_acceptance.py','p1_acceptance.py'): shutil.copy2(Path(__file__).with_name(name),root/name)
    shutil.copy2(REPO/'docs/schemas/jev-segment-v1.schema.json',root/'jev-segment-v1.schema.json')
    print('EVIDENCE_DIRECTORY='+str(root),flush=True)
    environment=os.environ.copy();environment.pop('JEV_API_KEY',None)
    if not mock:
        import sys
        sys.path.insert(0,str(REPO/'tools/probes'))
        from jev_client import load_jev_api_key
        environment['JEV_API_KEY']=load_jev_api_key(args.key_file)
    report=dict(phase=args.phase,plan_sha256=_sha256(root/'plan.json'),runs=[],status='RUNNING');server=None
    try:
        server=Server(root,args.artifact,environment,
                      f'http://127.0.0.1:{mock.server.server_port}' if mock else None,fixture_enabled=True)
        environment.pop('JEV_API_KEY',None);server.setup()
        for spec in plan['schedule']:
            config=dict(CONFIG)
            if mock:
                config['apiKey']='fixture-only-no-credential';config.update(spec.get('config',{}))
                mock.choice=spec['choice'];mock.fault=spec.get('fault');mock.requests=0
            trace=prepare(server,spec,config);wait_terminal(server,trace,spec.get('cancel',False),spec.get('late',False))
            if spec.get('late'): time.sleep(2.2)
            result=dict(condition=spec['condition'],mode=spec['mode'],repeat=spec['repeat'],trace=trace.name)
            try: result.update(summarize(trace),valid_trace=True)
            except EvidenceError as exc:
                result.update(valid_trace=False,status=events(trace)[-1]['data'].get('status'),verification_error=str(exc))
            report['runs'].append(result);_json(root/'verification.json',report)
            prior_observations=set((server.data/'traces').glob('observe-*.jsonl'))
            result['settled']=server.release_check()
            added_observations=set((server.data/'traces').glob('observe-*.jsonl'))-prior_observations
            if len(added_observations)!=1: raise EvidenceError('Missing settled observation')
            result['settled_trace']=added_observations.pop().name
            result['despawn_receipt']=server.command('jev despawn')
            if mock:
                result['mock_check']=result['status']==spec['expected'] and result['valid_trace']
                if spec.get('reason'):
                    result['mock_check'] &= any(c['reason']==spec['reason'] for c in result.get('cycles',[]))
                if spec.get('reason_any'):
                    result['mock_check'] &= any(c['reason'] in spec['reason_any'] for c in result.get('cycles',[]))
                if spec.get('ticks_expected') is not None: result['mock_check'] &= result.get('input_ticks')==spec['ticks_expected']
                if spec.get('fault'):
                    result['mock_check'] &= result.get('decisions')==1
            _json(root/'verification.json',report)
            print(json.dumps({k:result.get(k) for k in ('condition','mode','status','arrival','input_ticks','decisions','valid_trace','mock_check')}),flush=True)
            if not mock and result['status']=='ERROR': break
        passed=all(r['mock_check'] for r in report['runs']) if mock else verdict(report['runs'],args.phase,plan.get('development_cases'))
        report['status']='PASSED' if passed else 'CRITERIA_NOT_MET'
    except BaseException as exc:
        report['status']='HARNESS_ERROR';report['failure_type']=type(exc).__name__;raise
    finally:
        if server:
            try:
                server.command('jev stop')
                status=server.command('jev status')
                if not any('bot=none' in line for line in status['output']): server.command('jev despawn')
                report['cleanup']=dict(receipt=server.command('jev status'))
            except Exception: report['cleanup']=dict(failed=True);report['status']='HARNESS_ERROR'
            server.close()
        if mock: mock.server.shutdown();mock.server.server_close()
        _json(root/'verification.json',report)
        print('STATUS='+report['status'],flush=True)
    return 0 if report['status']=='PASSED' else 2


def smoke_schedule():
    specs=[dict(condition=n,mode='assisted',repeat=1,choice='W' if n.startswith('west') else 'E',expected='GOAL_REACHED',**p) for n,p in DIAGNOSTICS.items()]
    base=dict(mode='assisted',repeat=1,yaw=0,goal=[20.5,81,.5],choice='E',expected='BUDGET_EXCEEDED',config={'maxDecisions':1})
    specs += [dict(base,condition='wait',choice='WAIT',reason='WAIT_COMPLETED'),
              dict(base,condition='deadline',effect='effect give JevBot minecraft:slowness 10 5 true',reason='DEADLINE'),
              dict(base,condition='stall',effect='effect give JevBot minecraft:slowness 10 6 true',reason='STALLED'),
              dict(base,condition='cancel',cancel=True,expected='CANCELLED'),
              dict(base,condition='original-wall',wall=PRESETS['original-wall']['wall'],goal=[.5,81,20.5],choice='S',config={'maxDecisions':8})]
    specs += [dict(base,condition='static-block',static_block=True,reason_any=['OBSERVED_OBSTACLE','COLLISION']),
              dict(base,condition='assisted-tick-budget',goal=[60.5,81,.5],config={},ticks_expected=240),
              dict(base,condition='direct-tick-budget',mode='direct',choice='WAIT',config={},ticks_expected=240)]
    for fault in ('api','network','unknown','timeout','stale'):
        specs.append(dict(base,condition=fault,fault=fault,expected='ERROR',config={'timeoutSeconds':1} if fault=='timeout' else {'maxObservationAgeTicks':1} if fault=='stale' else {}))
    specs.append(dict(base,condition='late',fault='late',late=True,expected='CANCELLED',config={}))
    return specs


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=('diagnostic','development','final','smoke'),default='diagnostic')
    p.add_argument('--artifact',type=Path,default=REPO/'build/libs/jev-control-paper-0.2.0.jar')
    p.add_argument('--key-file',type=Path);p.add_argument('--diagnostic-directory',type=Path)
    p.add_argument('--development-case',action='append',choices=list(DIAGNOSTICS|PRESETS))
    p.add_argument('--hypothesis')
    p.add_argument('--rediagnostic-directory',type=Path)
    p.add_argument('--audit-directory',type=Path);p.add_argument('--execute',action='store_true')
    p.add_argument('--smoke-case',action='append',choices=[s['condition'] for s in smoke_schedule()]);args=p.parse_args()
    if args.smoke_case and args.phase!='smoke': p.error('--smoke-case applies only to dummy local tests')
    if args.development_case and args.phase!='development': p.error('Development cases require development phase')
    if args.audit_directory:
        result=audit(args.audit_directory);print(json.dumps(result));return 0 if result['passed'] else 2
    digest=_sha256(args.artifact) if args.artifact.is_file() else None
    if args.phase=='development' and (not args.development_case or not args.hypothesis): p.error('Development requires cases and a hypothesis')
    plan=dict(issue=40,phase=args.phase,contract=CONTRACT,schedule=smoke_schedule() if args.phase=='smoke' else schedule(args.phase,args.development_case),
              config={k:v for k,v in CONFIG.items() if k!='apiKey'},artifact_sha256=digest,artifact_filename=args.artifact.name,
              server_sha256=SERVER_SHA256,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              harness_sha256=_sha256(Path(__file__)))
    if args.phase=='development': plan.update(development_cases=args.development_case,hypothesis=args.hypothesis)
    plan['evaluator_files']={name:_sha256(Path(__file__).with_name(name)) for name in ('p1b_acceptance.py','paper_acceptance.py','p1_acceptance.py')}
    plan['evaluator_files']['jev-segment-v1.schema.json']=_sha256(REPO/'docs/schemas/jev-segment-v1.schema.json')
    if args.smoke_case: plan['schedule']=[s for s in plan['schedule'] if s['condition'] in args.smoke_case]
    if not args.execute: print(json.dumps(plan,indent=2));return 0
    if digest is None: p.error('Build artifact before execute')
    if args.phase!='smoke' and args.key_file is None: p.error('Live execution requires explicit --key-file')
    if args.phase=='final':
        if args.diagnostic_directory is None: p.error('Final requires audited diagnostic directory')
        diagnosis=audit(args.diagnostic_directory)
        if not diagnosis['passed'] or diagnosis['phase']!='diagnostic': p.error('Diagnostic prerequisite failed')
        if diagnosis['artifact_sha256']!=digest:
            if args.rediagnostic_directory is None: p.error('Changed artifact requires four development re-diagnostics')
            repeated=audit(args.rediagnostic_directory)
            repeated_plan=json.loads((args.rediagnostic_directory/'plan.json').read_text(encoding='utf-8'))
            if (not repeated['passed'] or repeated['phase']!='development' or repeated['artifact_sha256']!=digest
                    or repeated_plan.get('development_cases')!=list(DIAGNOSTICS)):
                p.error('Re-diagnostics must cover all four assisted conditions with the final artifact')
            plan['rediagnostic_directory']=str(args.rediagnostic_directory.resolve())
        plan['diagnostic_directory']=str(args.diagnostic_directory.resolve())
    return execute(args,plan)


if __name__=='__main__': raise SystemExit(main())
