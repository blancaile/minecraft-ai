"""Reconstruct public P1b metrics from retained raw evidence; never reads config credentials."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics

from p1b_acceptance import audit, summarize, events, _sha256, EvidenceError


def report(directories):
    output=dict(issue=40,format='p1b-public-results-v1',batches=[])
    for root in directories:
        plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
        recorded=json.loads((root/'verification.json').read_text(encoding='utf-8'))
        if plan['phase']=='smoke':
            checked=dict(passed=None,note='Live acceptance audit does not apply to mock smoke; per-trace checks below')
        else:
            try: checked=audit(root)
            except (EvidenceError,KeyError,ValueError) as exc: checked=dict(passed=False,error=str(exc))
        batch=dict(directory=str(root),availability='Raw JSONL, receipts and binaries retained locally only',
                   phase=plan['phase'],source_commit=plan['source_commit'],artifact_sha256=plan['artifact_sha256'],
                   plan_sha256=_sha256(root/'plan.json'),verification_sha256=_sha256(root/'verification.json'),
                   schedule=plan['schedule'],hypothesis=plan.get('hypothesis'),recorded_status=recorded['status'],audit=checked,runs=[])
        for recorded_run in recorded['runs']:
            path=root/'plugins/JevControl/traces'/recorded_run['trace'];rows=events(path)
            item={k:recorded_run[k] for k in ('condition','mode','repeat','trace')}
            try: item.update(summarize(path))
            except EvidenceError as exc:
                item.update(valid_trace=False,error=str(exc),status=rows[-1]['data'].get('status'),arrival=False,
                            decisions=rows[-1]['data'].get('decisions',0),input_ticks=rows[-1]['data'].get('input_ticks',0),
                            trace_sha256=_sha256(path))
            decisions=[r['data'] for r in rows if r['event']=='decision']
            item['api_requests']=sum(r['event']=='observation' for r in rows)
            item['actions']=dict(Counter(d['response']['choice'] for d in decisions))
            item['max_tick_gap_ms']=rows[-1]['data'].get('max_tick_gap_ms')
            item['snapshot_age_ticks']=[d['snapshot_age_ticks'] for d in decisions]
            latencies=sorted(d['latency_ms'] for d in decisions)
            item['latency_p50_ms']=statistics.median(latencies) if latencies else None
            item['latency_p95_ms']=latencies[math.ceil(len(latencies)*.95)-1] if latencies else None
            item['release_verified']=bool(recorded_run.get('settled')) and bool(recorded_run.get('despawn_receipt',{}).get('success'))
            result_rows=[r for r in rows if r['event'] in ('result','segment_result')]
            displacements=[r['data']['displacement'] for r in result_rows]
            item['path_length_during_input']=sum(r['data'].get('path_length',math.hypot(d[0],d[2])) for r,d in zip(result_rows,displacements))
            item['horizontal_reversals']=sum(a[0]*b[0]+a[2]*b[2]<-.01 for a,b in zip(displacements,displacements[1:]))
            item['final_position']=rows[-1]['data']['final']['position']
            item['interventions']=[dict(server_tick=r['server_tick'],**r['data']) for r in rows if r['event']=='fixture_intervention']
            batch['runs'].append(item)
        output['batches'].append(batch)
    runs=[r for b in output['batches'] for r in b['runs']]
    output['aggregate']=dict(runs=len(runs),decisions=sum(r.get('decisions',0) for r in runs),
                             api_requests=sum(r['api_requests'] for r in runs),
                             input_ticks=sum(r.get('input_ticks',0) for r in runs),
                             status_counts=dict(Counter(r['status'] for r in runs)))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directories',type=Path,nargs='+');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=report(args.directories)
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(value['aggregate']))
