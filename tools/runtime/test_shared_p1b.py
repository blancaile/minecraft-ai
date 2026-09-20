import unittest
from shared_p1b import trace_name, EvidenceError


class ReceiptBindingTests(unittest.TestCase):
    def test_status_and_observe_paths(self):
        self.assertEqual('abc.jsonl',trace_name({'output':['JEV_OK state=GOAL_REACHED trace=plugins/JevControl/traces/abc.jsonl']}))
        self.assertEqual('observe-abc.jsonl',trace_name({'output':['JEV_OK Observation written: plugins/JevControl/traces/observe-abc.jsonl']}))

    def test_start_acknowledgement_is_not_trace_evidence(self):
        with self.assertRaises(EvidenceError):
            trace_name({'output':['JEV_OK Jev run started']})


if __name__=='__main__':unittest.main()
