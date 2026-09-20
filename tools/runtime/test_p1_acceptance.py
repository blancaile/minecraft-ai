"""Offline P1a verifier checks.  These never start Paper or read credentials."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import copy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p1_acceptance as p1


def row(kind, tick, data): return {"event": kind, "server_tick": tick, "data": data}


class P1EvidenceTests(unittest.TestCase):
    def test_terminal_cannot_use_excessive_or_opposite_velocity(self):
        import copy
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for velocity in ([0, 0, 100], [0, 0, -.2]):
                records = self.trace()
                records[-2]["data"]["after"]["velocity"] = velocity
                records[-1]["data"]["final"] = copy.deepcopy(records[-2]["data"]["after"])
                records[-1]["data"]["final"]["position"][2] = 20.0
                records[-1]["server_tick"] = 41
                with self.assertRaises(p1.EvidenceError): p1.summarize(self.write_trace(root, "coast.jsonl", records))

    def test_policy_encoding_cannot_hide_unknowns_or_filter_candidates(self):
        state = {"legal_candidates": ["FORWARD", "BACK"], "local_cells": [
            {"position": [1, 81, 4], "knowledge": "UNKNOWN", "unknown_reason": "occluded"}]}
        state["policy_state"] = {"legal_candidates": ["FORWARD", "BACK"], "policy_encoding": "jev-cell-tables-v1",
            "observed_cell_columns": "world_x,world_y,world_z,block,fluid,local_collision_boxes,observed_tick; every row is OBSERVED",
            "unknown_cell_columns": "world_x,world_y,world_z,unknown_reason; every row is UNKNOWN, not empty space; unlisted cells are also UNKNOWN",
            "observed_cells": [], "unknown_cells": [[1, 81, 4, "occluded"]]}
        p1.verify_policy_encoding(state)
        state["policy_state"]["legal_candidates"] = ["FORWARD"]
        with self.assertRaises(p1.EvidenceError): p1.verify_policy_encoding(state)
        state["policy_state"]["legal_candidates"] = ["FORWARD", "BACK"]
        state["policy_state"]["unknown_cells"] = []
        with self.assertRaises(p1.EvidenceError): p1.verify_policy_encoding(state)

    def trace(self, *, arrival=True, wall=True, yaw=0):
        records = [row("run_started", 1, {"run_id": "run", "config": dict(p1.PUBLIC_CONFIG), "spawn": [.5, 81, .5],
                                             "goal": [.5, 81, 20.5], "artifact_sha256": "artifact", "policy": "JEV", "fault_fixture": False})]
        previous = {}
        for index in range(4):
            before = {"position": [.5, 81, .5 + index * 4.8], "yaw": yaw}
            after = {"position": [.5, 81, .5 + (index + 1) * 4.8 if arrival else .5], "yaw": yaw, "velocity": [0, 0, 0]}
            request_id, observation_tick = f"r{index}", 2 + index * 10
            cells = [{"position": [0, 81, 4], "knowledge": "OBSERVED", "block": "minecraft:stone"}] if wall and index == 3 else []
            records.extend([
                row("observation", observation_tick, {"observation_id": request_id, "legal_candidates": ["FORWARD", "WAIT"],
                                                        "previous": previous, "local_cells": cells, "self": before}),
                row("decision", observation_tick + 2, {"request_id": request_id, "latency_ms": 10, "response": {"choice": "FORWARD"}}),
                row("input", observation_tick + 2, {"request_id": request_id, "source": "JEV", "action": "FORWARD", "before": before}),
                row("result", observation_tick + 6, {"request_id": request_id, "action": "FORWARD", "actual_ticks": 4,
                                                       "after": after, "displacement": [0, 0, after["position"][2] - before["position"][2]]}),
            ])
            previous = records[-1]["data"]
        records.append(row("terminal", 38, {"status": "GOAL_REACHED" if arrival else "BUDGET_EXCEEDED", "reason": "test", "final": after,
                                              "elapsed_ms": 100, "decisions": 4}))
        return records

    def write_trace(self, directory, name, rows):
        trace_dir = directory / "plugins/JevControl/traces"; trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / name
        path.write_text("".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8")
        return path

    def test_summarize_rejects_forged_arrival_and_cycle(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); path = self.write_trace(root, "one.jsonl", self.trace())
            self.assertEqual(p1.summarize(path)["cycle_count"], 4)
            forged = self.trace(); forged[-1]["data"]["final"]["position"] = [.5, 81, 99]
            path.write_text("".join(json.dumps(item) + "\n" for item in forged), encoding="utf-8")
            with self.assertRaises(p1.EvidenceError): p1.summarize(path)
            forged = self.trace(); forged[4]["data"]["displacement"] = [9, 0, 9]
            path.write_text("".join(json.dumps(item) + "\n" for item in forged), encoding="utf-8")
            with self.assertRaises(p1.EvidenceError): p1.summarize(path)

    def test_summarize_rejects_terminal_only_arrival_and_overbudget_success(self):
        with tempfile.TemporaryDirectory() as raw:
            path = self.write_trace(Path(raw), "one.jsonl", self.trace(arrival=False))
            forged = p1.events(path); forged[-1]["data"].update(status="GOAL_REACHED", final={"position": [.5, 81, 20.5]})
            path.write_text("".join(json.dumps(item) + "\n" for item in forged), encoding="utf-8")
            with self.assertRaises(p1.EvidenceError): p1.summarize(path)

    def test_summarize_rejects_duplicate_observation_input_or_result_ids(self):
        with tempfile.TemporaryDirectory() as raw:
            path = self.write_trace(Path(raw), "one.jsonl", self.trace())
            for index in (1, 3, 4):
                forged = self.trace(); forged.insert(index + 1, copy.deepcopy(forged[index]))
                path.write_text("".join(json.dumps(item) + "\n" for item in forged), encoding="utf-8")
                with self.assertRaises(p1.EvidenceError): p1.summarize(path)
            forged = self.trace(); forged[-1]["data"]["elapsed_ms"] = 120001
            path.write_text("".join(json.dumps(item) + "\n" for item in forged), encoding="utf-8")
            with self.assertRaises(p1.EvidenceError): p1.summarize(path)

    def test_wall_requires_observation_choice_and_actual_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); path = self.write_trace(root, "one.jsonl", self.trace())
            intervention = {"kind": "wall", "wall": p1.WALL_ORIGINAL, "after_tick": 28, "after_completed_cycles": 3}
            self.assertTrue(p1.wall_evidence(path, intervention)["wall_observed_and_executed"])
            with self.assertRaises(p1.EvidenceError): p1.wall_evidence(self.write_trace(root, "two.jsonl", self.trace(wall=False)), intervention)
            rows = self.trace(); rows.pop(4)
            with self.assertRaises(p1.EvidenceError): p1.wall_evidence(self.write_trace(root, "three.jsonl", rows), intervention)

    def test_final_verdict_needs_two_arrivals_and_all_wall_executions(self):
        plan = {"presets": list(p1.PRESETS), "repeats": 3}
        runs = []
        for preset in p1.PRESETS:
            for number in range(3): runs.append({"preset": preset, "arrival": number < 2, "wall_execution": True})
        self.assertTrue(p1._final_verdict(runs, plan)["passed"])
        runs[-1]["wall_execution"] = False
        self.assertFalse(p1._final_verdict(runs, plan)["passed"])
        self.assertFalse(p1._final_verdict(runs[:-1], plan)["passed"])

    def test_audit_rejects_missing_runs_and_tampered_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            plan = {"format": "p1a-acceptance-v1", "phase": "final", "repeats": 3, "presets": list(p1.PRESETS),
                    "preset_definitions": p1.PRESETS, "spawn": [.5, 81, .5], "config": dict(p1.PUBLIC_CONFIG), "artifact_sha256": "artifact", "criteria": {},
                    "harness_sha256": p1._sha256(Path(p1.__file__))}
            p1._json(root / "plan.json", plan)
            report = {"format": "p1a-report-v1", "plan_sha256": hashlib.sha256((root / "plan.json").read_bytes()).hexdigest(),
                      "artifact_sha256": "artifact", "runs": [], "cleanup": {"verified_no_bot": True}, "final_criterion": {"passed": True}}
            p1._json(root / "verification.json", report)
            with self.assertRaises(p1.EvidenceError): p1.audit_directory(root)
            report["artifact_sha256"] = "tampered"; p1._json(root / "verification.json", report)
            with self.assertRaises(p1.EvidenceError): p1.audit_directory(root)

    def test_audit_accepts_reconstructed_final_then_rejects_trace_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); shutil.copy2(Path(p1.__file__), root / "p1_acceptance.py")
            plugin_dir = root / "plugins"; plugin_dir.mkdir(exist_ok=True); (plugin_dir / "artifact.jar").write_bytes(b"artifact")
            artifact_hash = p1._sha256(plugin_dir / "artifact.jar")
            definitions = p1.PRESETS
            plan = {"format": "p1a-acceptance-v1", "phase": "final", "repeats": 3, "presets": list(p1.PRESETS),
                    "preset_definitions": definitions, "spawn": [.5, 81, .5], "config": dict(p1.PUBLIC_CONFIG), "artifact_sha256": artifact_hash,
                    "artifact_filename": "artifact.jar", "criteria": p1.CRITERIA,
                    "harness_sha256": p1._sha256(root / "p1_acceptance.py")}
            p1._json(root / "plan.json", plan)
            runs = []
            receipt_dir = root / "plugins/JevControl/receipts"; receipt_dir.mkdir(parents=True)
            receipt_time = 1
            for preset in p1.PRESETS:
                for repeat in range(1, 4):
                    trace = self.write_trace(root, f"{preset}-{repeat}.jsonl", self.trace())
                    rows = self.trace(yaw=p1.PRESETS[preset]["yaw"]); rows[0]["data"].update(run_id=f"{preset}-{repeat}", artifact_sha256=artifact_hash)
                    trace = self.write_trace(root, f"{preset}-{repeat}.jsonl", rows)
                    intervention = {"kind": "wall", "wall": p1.PRESETS[preset]["wall"], "after_tick": 28, "after_completed_cycles": 3}
                    p1._json(root / f"{trace.stem}-intervention.json", intervention)
                    summary = p1.summarize(trace); summary.update(trace_path=str(trace), preset=preset, repeat=repeat)
                    assessment = p1._run_assessment(summary, intervention); assessment.pop("trace_path"); assessment["valid_trace"] = True
                    assessment["intervention_file"] = f"{trace.stem}-intervention.json"
                    receipt = {"id": f"despawn-{preset}-{repeat}", "success": True, "output": ["Despawn requested"], "completed_at_ms": receipt_time}
                    receipt_time += 1; p1._json(receipt_dir / f"{receipt['id']}.json", receipt); assessment["despawn_receipt"] = receipt
                    runs.append(assessment)
            status_receipt = {"id": "status", "success": True, "output": ["state=READY bot=none"], "completed_at_ms": receipt_time}
            p1._json(receipt_dir / "status.json", status_receipt)
            report = {"format": "p1a-report-v1", "plan_sha256": hashlib.sha256((root / "plan.json").read_bytes()).hexdigest(),
                      "artifact_sha256": plan["artifact_sha256"], "runs": runs,
                      "cleanup": {"verified_no_bot": True, "status_receipt": status_receipt},
                      "final_criterion": p1._final_verdict(runs, plan)}
            p1._json(root / "verification.json", report)
            self.assertEqual(p1.audit_directory(root)["status"], "PASSED")
            obsolete = dict(status_receipt, completed_at_ms=0)
            p1._json(receipt_dir / "status.json", obsolete); report["cleanup"] = {"verified_no_bot": True, "status_receipt": obsolete}
            p1._json(root / "verification.json", report)
            with self.assertRaises(p1.EvidenceError): p1.audit_directory(root)
            p1._json(receipt_dir / "status.json", status_receipt); report["cleanup"] = {"verified_no_bot": True, "status_receipt": status_receipt}
            p1._json(root / "verification.json", report)
            trace = root / "plugins/JevControl/traces/original-wall-1.jsonl"; records = p1.events(trace)
            records[0]["data"]["artifact_sha256"] = "tampered"
            trace.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            with self.assertRaises(p1.EvidenceError): p1.audit_directory(root)

    def test_fixed_final_plan_rejects_easy_goal_missing_preset_and_vacuous_pass(self):
        import copy
        plan = {"phase": "final", "repeats": 3, "presets": list(p1.PRESETS),
                "preset_definitions": copy.deepcopy(p1.PRESETS), "criteria": dict(p1.CRITERIA)}
        p1.validate_plan(plan)
        easy = copy.deepcopy(plan); easy["preset_definitions"]["original-wall"]["goal"][2] = 1.5
        with self.assertRaises(p1.EvidenceError): p1.validate_plan(easy)
        for names in ([], ["original-wall"], ["original-wall"] * 3):
            altered = dict(plan, presets=names)
            with self.assertRaises(p1.EvidenceError): p1.validate_plan(altered)
        self.assertFalse(p1._final_verdict([], {"presets": [], "repeats": 3})["passed"])


if __name__ == "__main__": unittest.main()
