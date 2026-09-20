"""Bounded shared-server assisted validation using configured credentials and unchanged terrain."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from p1b_acceptance import summarize, events, EvidenceError
from p1_acceptance import REPO, _json, _sha256

CASES=[dict(name=name,offset=offset,cancel=cancel) for name,offset,cancel in (
    ('south',[0,0,3],False),('east',[1.25,0,0],False),('west',[-1.25,0,0],False),
    ('north',[0,0,-1.25],False),('cancel',[0,0,5],True))]


def trace_name(receipt):
    match=re.search(r'(?:trace=|Observation written: )\S*[/\\]([a-zA-Z0-9-]+\.jsonl)', ' '.join(receipt['output']))
    if not match: raise EvidenceError('Receipt has no trace binding')
    return match[1]


def public_config(receipt):
    return json.loads(receipt['output'][0].removeprefix('JEV_OK '))


def audit(root):
    plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
    report=json.loads((root/'shared-experiment.json').read_text(encoding='utf-8'))
    if report['plan_sha256']!=_sha256(root/'plan.json') or plan['cases']!=CASES:
        raise EvidenceError('Shared plan binding')
    if report['cleanup_errors'] or report['status']!='PENDING_AUDIT' or len(report['runs'])!=len(CASES):
        raise EvidenceError('Incomplete shared campaign or cleanup')
    for name,digest in plan['evaluator_files'].items():
        if _sha256(root/name)!=digest: raise EvidenceError('Evaluator snapshot changed')
    for receipt in report['receipts']:
        raw=json.loads((root/(receipt['result']['id']+'.receipt.json')).read_text(encoding='utf-8'))
        if raw!=receipt['result'] or not raw['success']: raise EvidenceError('Receipt differs from server evidence')
    def command(value):
        return [r['result'] for r in report['receipts'] if r['command']==value]
    if not all('bot=none' in ' '.join(r['output']) for r in (command('jev status')[0],command('jev status')[-1])):
        raise EvidenceError('Initial/final bot absence missing')
    before,after=map(public_config,command('jev key-status'))
    if before!=after or not after['configured'] or after['model']!='jev-1.13.0':
        raise EvidenceError('Configured credential or config changed')
    checked=[]
    for index,(run,spec) in enumerate(zip(report['runs'],CASES)):
        if run['case']!=spec: raise EvidenceError('Run order changed')
        for name in ('start','terminal','settled','despawn','cancel_receipt'):
            if name in run and run[name] not in [r['result'] for r in report['receipts']]:
                raise EvidenceError('Run uses an unbound receipt')
        terminal=run['terminal']; path=root/trace_name(terminal); value=summarize(path)
        site=run['site']; spawn=site['spawn_position']; expected=[a+b for a,b in zip(spawn,spec['offset'])]
        actual_site=json.loads(command('jev spawn-near '+plan['player'])[index]['output'][0].removeprefix('JEV_OK Spawned JevBot '))
        if site!=actual_site: raise EvidenceError('Spawn site differs from server receipt')
        if (value['mode']!='assisted' or value['fault_fixture'] or value['artifact_sha256']!=plan['artifact_sha256']
                or plan['artifact_sha256'] not in ' '.join(terminal['output']) or site['terrain_changed']
                or math.dist(value['spawn'],spawn)>1e-8 or math.dist(value['initial']['position'],spawn)>.05
                or math.dist(value['goal'],expected)>1e-8 or value['config']['model']!='jev-1.13.0'
                or value['config']['goalRadius']!=1 or value['elapsed_ms']>120000):
            raise EvidenceError('Shared run differs from plan or actual spawn')
        if spec['cancel']:
            if value['status']!='CANCELLED' or value['input_ticks']<1 or not run.get('cancel_receipt'):
                raise EvidenceError('Cancellation did not interrupt actual movement')
        elif not value['arrival'] or value['input_ticks']<1 or value['decisions']<1:
            raise EvidenceError('Real movement and arrival required')
        rows=events(root/trace_name(run['settled']))
        physical=rows[0]['data']['self']
        raw=events(path)
        initial_observation=next(r for r in raw if r['event']=='observation')
        if (rows[0]['server_tick']<raw[-1]['server_tick'] or rows[0]['data']['bot_id']!=initial_observation['data']['bot_id']
                or rows[0]['data']['goal']['position']!=value['goal']):
            raise EvidenceError('Settled observation belongs to a different bot, goal or time')
        if math.hypot(physical['velocity'][0],physical['velocity'][2])>=.001 or physical['health']<=0:
            raise EvidenceError('Physical release or survival failed')
        if not run['despawn']['success']: raise EvidenceError('Despawn failed')
        value.update(condition=spec['name'],settled=physical,settled_trace_sha256=_sha256(root/trace_name(run['settled'])))
        checked.append(value)
    return dict(passed=True,issue=40,artifact_sha256=plan['artifact_sha256'],source_commit=plan['source_commit'],
                plan_sha256=_sha256(root/'plan.json'),manifest_sha256=_sha256(root/'shared-experiment.json'),runs=checked,
                config_preserved=True,terrain_changed=False,final_bot_absent=True)


def execute(args):
    run_id='p1b-shared-'+uuid.uuid4().hex[:12]
    root=REPO/'.runtime-harness'/('remote-'+run_id);root.mkdir(parents=True)
    plan=dict(issue=40,cases=CASES,player=args.player,artifact_sha256=_sha256(args.artifact),
              source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              max_runs=5,max_decisions_per_run=60,max_seconds_per_run=120,max_input_ticks_per_run=240,
              environment='shared server; existing configured credential; no terrain changes',evaluator_files={})
    for name in ('shared_p1b.py','p1b_acceptance.py','p1_acceptance.py','paper_acceptance.py','remote.ps1'):
        source=Path(__file__).with_name(name);shutil.copy2(source,root/name);plan['evaluator_files'][name]=_sha256(source)
    schema=REPO/'docs/schemas/jev-segment-v1.schema.json';shutil.copy2(schema,root/schema.name)
    plan['evaluator_files'][schema.name]=_sha256(schema)
    _json(root/'plan.json',plan)
    report=dict(status='RUNNING',plan_sha256=_sha256(root/'plan.json'),runs=[],receipts=[],cleanup_errors=[])
    print('EVIDENCE_DIRECTORY='+str(root),flush=True)
    owns_bot=False
    def save(): _json(root/'shared-experiment.json',report)
    def remote(action,command=None):
        cmd=['powershell','-NoProfile','-File',str(REPO/'tools/runtime/remote.ps1'),'-Action',action,'-RunId',run_id]
        if command: cmd+=['-Command',command]
        result=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='replace',timeout=65)
        if result.returncode: raise EvidenceError('Remote '+action+' failed: '+result.stderr[-1200:])
        value=json.loads(result.stdout)
        if command: report['receipts'].append(dict(command=command,result=value));save()
        return value
    try:
        status=remote('Command','jev status')
        if 'bot=none' not in ' '.join(status['output']): raise EvidenceError('Existing bot; refusing takeover')
        if plan['artifact_sha256'] not in ' '.join(status['output']): raise EvidenceError('Active JAR mismatch')
        configured=public_config(remote('Command','jev key-status'))
        if not configured['configured'] or configured['model']!='jev-1.13.0' or configured['goalRadius']!=1:
            raise EvidenceError('Shared credential/model/radius prerequisite failed')
        for spec in CASES:
            run=dict(case=spec);report['runs'].append(run);save()
            owns_bot=True
            spawn=remote('Command','jev spawn-near '+args.player)
            site=json.loads(spawn['output'][0].removeprefix('JEV_OK Spawned JevBot '));run['site']=site
            goal=[a+b for a,b in zip(site['spawn_position'],spec['offset'])]
            remote('Command','jev goal '+' '.join(map(str,goal))+' '+site['world'])
            run['start']=remote('Command','jev start assisted');save()
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                time.sleep(.15)
                status=remote('Command','jev status');state=' '.join(status['output'])
                if re.search(r'state=(GOAL_REACHED|BUDGET_EXCEEDED|CANCELLED|ERROR|DEAD_OR_DISCONNECTED)',state):break
                match=re.search(r'decisions=(\d+)',state)
                if spec['cancel'] and not run.get('cancel_receipt') and match and int(match[1])>=1:
                    run['cancel_receipt']=remote('Command','jev stop');save()
            else: raise EvidenceError('Shared wall-clock budget exceeded')
            run['terminal']=status;save()
            if ('state=CANCELLED' if spec['cancel'] else 'state=GOAL_REACHED') not in state:
                raise EvidenceError('Shared run did not meet expected terminal state')
            time.sleep(2)
            run['settled']=remote('Command','jev observe')
            run['despawn']=remote('Command','jev despawn');owns_bot=False;save()
            print(json.dumps(dict(condition=spec['name'],terminal=state.split(' reason=')[0])),flush=True)
        remote('Command','jev key-status')
        remote('Command','jev status')
        report['status']='PENDING_AUDIT'
    except BaseException as exc:
        report.update(status='FAILED',failure=str(exc));raise
    finally:
        if owns_bot:
            for command in ('jev stop','jev despawn','jev status'):
                try: remote('Command',command)
                except Exception as exc: report['cleanup_errors'].append(str(exc))
        for action in ('Log','Traces'):
            try: remote(action)
            except Exception as exc: report['cleanup_errors'].append(str(exc))
        save()
    result=audit(root);_json(root/'shared-audit.json',result)
    print(json.dumps(dict(passed=result['passed'],runs=len(result['runs']),directory=str(root))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--player',default='Philia_Gray')
    parser.add_argument('--artifact',type=Path,default=REPO/'build/libs/jev-control-paper-0.2.0.jar')
    parser.add_argument('--audit-directory',type=Path);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.audit_directory:
        result=audit(args.audit_directory);print(json.dumps(result,indent=2))
    elif args.execute:
        if not re.fullmatch(r'[A-Za-z0-9_]{1,16}',args.player):parser.error('Invalid player')
        execute(args)
    else: print(json.dumps(dict(cases=CASES,max_runs=5,max_decisions=300,max_seconds=600,max_input_ticks=1200),indent=2))
