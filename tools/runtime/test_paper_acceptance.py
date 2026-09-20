"""Offline checks: a successful status cannot bypass cycle evidence validation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from paper_acceptance import summarize


class EvidenceTests(unittest.TestCase):
    def trace(self):
        before=dict(position=[0,81,0],yaw=0)
        after=dict(position=[0,81,.7],yaw=0)
        def row(kind,tick,data):return dict(event=kind,server_tick=tick,data=data)
        return [row('run_started',1,dict(config=dict(actionTicks=4,maxObservationAgeTicks=200,goalRadius=1),
                        goal=[0,81,1],artifact_sha256='test',fault_fixture=False)),
                row('observation',2,dict(observation_id='one',legal_candidates=['FORWARD','WAIT'],previous={})),
                row('decision',4,dict(request_id='one',latency_ms=100,response=dict(choice='FORWARD'))),
                row('input',4,dict(request_id='one',source='JEV',action='FORWARD',before=before)),
                row('result',8,dict(request_id='one',action='FORWARD',actual_ticks=4,after=after,displacement=[0,0,.7])),
                row('terminal',8,dict(status='GOAL_REACHED',reason='within radius',final=after,max_tick_gap_ms=50))]

    def run_summary(self,rows):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.jsonl'
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            return summarize(path)

    def test_valid_cycle(self):
        self.assertEqual(self.run_summary(self.trace())['cycles'],1)

    def test_forged_result_or_choice_or_ticks_or_goal_rejected(self):
        cases=[]
        for index,key,value in [(4,'displacement',[0,0,8]),(4,'actual_ticks',5),(3,'action','WAIT')]:
            rows=self.trace();rows[index]['data'][key]=value;cases.append(rows)
        rows=self.trace();rows[0]['data']['goal']=[100,81,100];cases.append(rows)
        rows=self.trace();rows[1]['data']['legal_candidates']=['WAIT'];cases.append(rows)
        for rows in cases:
            with self.assertRaises(AssertionError):self.run_summary(rows)

    def test_next_observation_must_bind_actual_previous_result(self):
        rows=self.trace();next_cycle=copy.deepcopy(rows[1:5])
        for row in next_cycle:
            row['server_tick']+=10
            row['data']['observation_id' if row['event']=='observation' else 'request_id']='two'
        rows[-1]['server_tick']=18
        rows[-1:-1]=next_cycle
        with self.assertRaises(AssertionError):self.run_summary(rows)
        rows[5]['data']['previous']=rows[4]['data']
        self.assertEqual(self.run_summary(rows)['cycles'],2)


if __name__=='__main__':unittest.main()
