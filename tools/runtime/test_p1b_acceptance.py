import copy
import json
from pathlib import Path
import tempfile
import unittest
import p1b_acceptance as p


class EvidenceTests(unittest.TestCase):
    def fixture(self):
        state=dict(position=[.5,81,.5],velocity=[0,0,0],yaw=0,pitch=0,on_ground=True,health=20,hunger=20,horizontal_collision=False,body_tick=10)
        selected=dict(id='WAIT',endpoint=[.5,81,.5],max_ticks=4,kind='WAIT')
        common=dict(schema_version='jev-segment-v1',segment_id='18723e82-cf06-4260-a995-14b4307234fe',request_id='r',selected=selected)
        def row(kind,tick,data):return dict(schema_version='jev-control-trace-v1',event=kind,server_tick=tick,time='2026-09-20T00:00:00Z',data=data)
        return [row('run_started',0,dict(run_id='run',execution_mode='assisted',artifact_sha256='abc',fault_fixture=False,
                    config={k:v for k,v in p.CONFIG.items() if k!='apiKey'},spawn=[.5,81,.5],goal=[3.5,81,.5])),
                row('observation',1,dict(observation_id='r',self=state,previous={},legal_candidates=['WAIT'],point_candidates=[selected],local_cells=[])),
                row('decision',2,dict(request_id='r',response={'choice':'WAIT'},latency_ms=1)),
                row('segment_start',2,dict(common,before=state,max_ticks=4)),
                *[row('segment_tick',i,dict(common,before=dict(state,body_tick=10+i-2),yaw=0,forward=0,strafe=0,jump=False,correction_reason='SELECTED_WAIT')) for i in range(2,6)],
                row('segment_result',6,dict(common,actual_ticks=4,reason='WAIT_COMPLETED',path_length=0,after=dict(state,body_tick=14),displacement=[0,0,0])),
                row('terminal',6,dict(status='BUDGET_EXCEEDED',input_ticks=4,decisions=1,elapsed_ms=200,final=state))]

    def check(self,rows):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'trace.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            return p.summarize(path)

    def test_valid_wait_is_not_arrival(self):
        result=self.check(self.fixture());self.assertFalse(result['arrival']);self.assertEqual(4,result['input_ticks'])

    def test_destination_substitution_rejected(self):
        rows=copy.deepcopy(self.fixture());rows[5]['data']['selected']=dict(rows[5]['data']['selected'],endpoint=[2,81,.5])
        with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_missing_and_duplicate_ticks_rejected(self):
        for duplicate in (False,True):
            rows=self.fixture()
            if duplicate:rows.insert(5,copy.deepcopy(rows[4]))
            else:rows.pop(4)
            with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_unknown_input_and_late_action_rejected(self):
        rows=self.fixture();rows[4]['data']['forward']=1
        with self.assertRaises(p.EvidenceError):self.check(rows)
        rows=self.fixture();rows[-2]['server_tick']=7
        with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_false_arrival_and_budget_rejected(self):
        rows=self.fixture();rows[-1]['data']['status']='GOAL_REACHED'
        with self.assertRaises(p.EvidenceError):self.check(rows)
        rows=self.fixture();rows[-1]['data']['input_ticks']=241
        with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_schema_unknown_fields_rejected(self):
        rows=self.fixture();rows[4]['data']['automatic_detour']=True
        with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_cancel_counts_consumed_body_ticks_even_with_same_server_tick(self):
        rows=self.fixture();rows[-2]['server_tick']=5;rows[-1]['server_tick']=5
        rows[-2]['data']['reason']='CANCELLED';rows[-1]['data']['status']='CANCELLED'
        result=self.check(rows);self.assertEqual(4,result['input_ticks'])

    def test_terminal_cannot_invent_motion_after_release(self):
        rows=copy.deepcopy(self.fixture());rows[-1]['data']['final']=dict(rows[-1]['data']['final'],position=[3.5,81,.5])
        rows[-1]['data']['status']='GOAL_REACHED'
        with self.assertRaises(p.EvidenceError):self.check(rows)

    def test_schedule_and_gate_require_complete_real_trials(self):
        self.assertEqual(8,len(p.schedule('diagnostic')));self.assertEqual(18,len(p.schedule('final')))
        specs=p.schedule('final');self.assertEqual(9,sum(s['mode']=='assisted' for s in specs))
        self.assertFalse(p.verdict([], 'diagnostic'))
        runs=[dict(s,arrival=True,valid_trace=True,settled={'health':20},fault_fixture=True) for s in p.schedule('diagnostic')]
        self.assertFalse(p.verdict(runs,'diagnostic'))
        for r in runs:r['fault_fixture']=False
        self.assertTrue(p.verdict(runs,'diagnostic'));runs[1]['arrival']=False
        self.assertFalse(p.verdict(runs,'diagnostic'))


if __name__=='__main__':unittest.main()
