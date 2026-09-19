from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from harness.gate_a.schema_validate import (
    EXAMPLES_DIR,
    SCHEMA_PATH,
    load_json,
    load_schema,
    validation_errors,
)


class GateASchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema()

    def test_schema_has_all_required_document_types(self) -> None:
        expected = {
            "contract",
            "run_manifest",
            "event",
            "mutation",
            "terminal",
            "result",
            "suite_summary",
        }
        actual = {
            load_json(path)["document_type"]
            for path in (EXAMPLES_DIR / "valid").glob("*.json")
        }
        self.assertEqual(expected, actual)

    def test_all_valid_examples_pass(self) -> None:
        paths = sorted((EXAMPLES_DIR / "valid").glob("*.json"))
        self.assertEqual(7, len(paths))
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual([], validation_errors(load_json(path), self.schema))

    def test_all_invalid_examples_fail(self) -> None:
        paths = sorted((EXAMPLES_DIR / "invalid").glob("*.json"))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertTrue(validation_errors(load_json(path), self.schema))

    def test_pass_rejects_each_nonzero_safety_counter(self) -> None:
        valid = load_json(EXAMPLES_DIR / "valid" / "result.json")
        for counter in valid["safety_counters"]:
            document = copy.deepcopy(valid)
            document["safety_counters"][counter] = 1
            with self.subTest(counter=counter):
                errors = validation_errors(document, self.schema)
                self.assertTrue(any(counter in error for error in errors))

    def test_pass_rejects_recovery_budget_overrun(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "result.json")
        document["recovery_budget"]["observed_episodes"] = 3
        document["recovery_budget"]["observed_seconds"] = 61
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("observed_episodes" in error for error in errors))
        self.assertTrue(any("observed_seconds" in error for error in errors))

    def test_pass_rejects_timeout_and_stall_overrun(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "result.json")
        document["timing"]["elapsed_seconds"] = 181
        document["timing"]["max_no_progress_seconds"] = 31
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("elapsed_seconds" in error for error in errors))
        self.assertTrue(any("max_no_progress_seconds" in error for error in errors))

    def test_pass_rejects_terminal_identity_mismatch(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "result.json")
        document["candidate_terminal"]["correlation_id"] = "different-mission"
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("candidate_terminal.correlation_id" in error for error in errors))

    def test_fixed_seed_must_match_requested_seed(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "run-manifest.json")
        document["seed"]["actual"] = 202
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("fixed seed" in error for error in errors))

    def test_manifest_component_names_must_be_unique(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "run-manifest.json")
        document["harness_components"][0]["name"] = document["candidate"]["name"]
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("component names must be unique" in error for error in errors))

    def test_gate_pass_rejects_decision_subset(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "suite-summary.json")
        document["suite_kind"] = "decision"
        document["gate_decision"] = "PASS"
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("suite_kind full" in error for error in errors))

    def test_gate_pass_rejects_incomplete_scenario_set(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "suite-summary.json")
        document["gate_decision"] = "PASS"
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("exact v1 scenario set" in error for error in errors))

    def test_summary_counts_must_match_listed_runs(self) -> None:
        document = load_json(EXAMPLES_DIR / "valid" / "suite-summary.json")
        document["scenario_aggregates"][0]["passes"] = 0
        document["scenario_aggregates"][0]["failures"] = 1
        document["scenario_aggregates"][0]["threshold_met"] = False
        errors = validation_errors(document, self.schema)
        self.assertTrue(any("does not match listed runs" in error for error in errors))

    def test_schema_does_not_encode_pinned_candidate_internals(self) -> None:
        serialized = json.dumps(self.schema, sort_keys=True).lower()
        for forbidden in ("mc_aiplayer", "zoyluo", "taskmanager", "goalexecutor"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_cli_returns_contract_error_for_invalid_instance(self) -> None:
        invalid = EXAMPLES_DIR / "invalid" / "result-false-pass.json"
        completed = subprocess.run(
            [sys.executable, "-m", "harness.gate_a.schema_validate", "instance", str(invalid)],
            cwd=SCHEMA_PATH.parents[3],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(5, completed.returncode)
        self.assertIn("INVALID", completed.stderr)


if __name__ == "__main__":
    unittest.main()
