"""Validate Gate A schema documents without importing a body candidate.

Exit codes intentionally follow Gate A Contract v1:
0 = valid, 4 = validator/tool failure, 5 = invalid contract/config/document.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PACKAGE_DIR / "schema" / "gate-a-v1.schema.json"
EXAMPLES_DIR = PACKAGE_DIR / "schema" / "examples"


class DocumentValidationError(ValueError):
    """Raised when a document violates schema or cross-field semantics."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schema() -> dict[str, Any]:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return schema


def _format_path(parts: Iterable[Any]) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def schema_errors(document: Any, schema: dict[str, Any] | None = None) -> list[str]:
    validator = Draft202012Validator(
        schema or load_schema(),
        format_checker=FormatChecker(),
    )
    return [
        f"{_format_path(error.absolute_path)}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]


def _contract_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    identifiers: set[str] = set()
    for index, scenario in enumerate(document["scenarios"]):
        prefix = f"$.scenarios[{index}]"
        identifier = scenario["scenario_id"]
        if identifier in identifiers:
            errors.append(f"{prefix}.scenario_id: duplicate scenario ID {identifier!r}")
        identifiers.add(identifier)
        threshold = scenario["threshold"]
        if threshold["total_runs"] != scenario["valid_runs"]:
            errors.append(
                f"{prefix}.threshold.total_runs: must equal valid_runs "
                f"({scenario['valid_runs']})"
            )
        if threshold["minimum_passes"] > threshold["total_runs"]:
            errors.append(f"{prefix}.threshold.minimum_passes: exceeds total_runs")
    return errors


def _manifest_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if (
        document["seed"]["policy"] == "fixed"
        and document["seed"]["requested"] != document["seed"]["actual"]
    ):
        errors.append("$.seed.actual: fixed seed must equal requested seed")
    if document["seed"]["policy"] == "not_applicable" and (
        document["seed"]["requested"] is not None or document["seed"]["actual"] is not None
    ):
        errors.append("$.seed: not_applicable requires requested and actual to be null")
    return errors


def _result_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    terminal = document.get("candidate_terminal") or {}
    if terminal and terminal.get("run_id") != document["run_id"]:
        errors.append("$.candidate_terminal.run_id: must equal result run_id")
    if terminal and terminal.get("correlation_id") != document["correlation_id"]:
        errors.append("$.candidate_terminal.correlation_id: must equal result correlation_id")
    postcondition_ids = [item["postcondition_id"] for item in document["postconditions"]]
    if len(postcondition_ids) != len(set(postcondition_ids)):
        errors.append("$.postconditions: duplicate postcondition_id")
    if document["outcome"] != "PASS":
        return errors

    if terminal.get("terminal_state") != "COMPLETED":
        errors.append("$.candidate_terminal: PASS requires candidate terminal COMPLETED")
    failed = [item["postcondition_id"] for item in document["postconditions"] if not item["passed"]]
    if failed:
        errors.append(f"$.postconditions: PASS contains failed postconditions {failed}")
    if document["violations"]:
        errors.append("$.violations: PASS cannot contain violations")

    counters = document["safety_counters"]
    for field, value in counters.items():
        if value != 0:
            errors.append(f"$.safety_counters.{field}: PASS requires zero, got {value}")

    budget = document["recovery_budget"]
    if budget["observed_episodes"] > budget["max_episodes"]:
        errors.append("$.recovery_budget.observed_episodes: exceeds max_episodes")
    if budget["observed_seconds"] > budget["max_seconds"]:
        errors.append("$.recovery_budget.observed_seconds: exceeds max_seconds")
    timing = document["timing"]
    if timing["elapsed_seconds"] > timing["mission_timeout_seconds"]:
        errors.append("$.timing.elapsed_seconds: exceeds mission_timeout_seconds")
    if timing["max_no_progress_seconds"] > timing["stall_window_seconds"]:
        errors.append("$.timing.max_no_progress_seconds: exceeds stall_window_seconds")
    return errors


def _summary_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runs_by_scenario: dict[str, list[dict[str, Any]]] = {}
    run_ids: set[str] = set()
    for index, run in enumerate(document["runs"]):
        if run["run_id"] in run_ids:
            errors.append(f"$.runs[{index}].run_id: duplicate run ID {run['run_id']!r}")
        run_ids.add(run["run_id"])
        runs_by_scenario.setdefault(run["scenario_id"], []).append(run)

    identifiers: set[str] = set()
    for index, aggregate in enumerate(document["scenario_aggregates"]):
        prefix = f"$.scenario_aggregates[{index}]"
        identifier = aggregate["scenario_id"]
        if identifier in identifiers:
            errors.append(f"{prefix}.scenario_id: duplicate scenario aggregate {identifier!r}")
        identifiers.add(identifier)
        counted = (
            aggregate["passes"]
            + aggregate["failures"]
            + aggregate["blocked"]
            + aggregate["harness_errors"]
        )
        if counted != aggregate["scheduled_runs"]:
            errors.append(f"{prefix}: outcome counts must equal scheduled_runs")
        expected_threshold = aggregate["passes"] >= aggregate["minimum_passes"]
        if aggregate["threshold_met"] != expected_threshold:
            errors.append(f"{prefix}.threshold_met: inconsistent with passes/minimum_passes")
        listed = runs_by_scenario.get(identifier, [])
        expected_counts = {
            "passes": sum(item["outcome"] == "PASS" for item in listed),
            "failures": sum(item["outcome"] == "FAIL" for item in listed),
            "blocked": sum(item["outcome"] == "BLOCKED" for item in listed),
            "harness_errors": sum(item["outcome"] == "HARNESS_ERROR" for item in listed),
        }
        if len(listed) != aggregate["scheduled_runs"]:
            errors.append(f"{prefix}.scheduled_runs: does not match listed runs")
        for field, expected in expected_counts.items():
            if aggregate[field] != expected:
                errors.append(f"{prefix}.{field}: does not match listed runs ({expected})")

    unknown_scenarios = set(runs_by_scenario) - identifiers
    if unknown_scenarios:
        errors.append(f"$.runs: scenarios without aggregate {sorted(unknown_scenarios)}")

    if document["gate_decision"] == "PASS":
        if document["suite_kind"] != "full":
            errors.append("$.gate_decision: PASS is valid only for suite_kind full")
        if document["zero_tolerance_failures"] != 0:
            errors.append("$.zero_tolerance_failures: Gate PASS requires zero")
        if any(not item["threshold_met"] for item in document["scenario_aggregates"]):
            errors.append("$.scenario_aggregates: Gate PASS requires every threshold_met")
        if any(
            item["blocked"] or item["harness_errors"]
            for item in document["scenario_aggregates"]
        ):
            errors.append("$.scenario_aggregates: Gate PASS forbids blocked or harness errors")
    return errors


def semantic_errors(document: dict[str, Any]) -> list[str]:
    handlers = {
        "contract": _contract_errors,
        "run_manifest": _manifest_errors,
        "result": _result_errors,
        "suite_summary": _summary_errors,
    }
    handler = handlers.get(document.get("document_type"))
    return handler(document) if handler else []


def validation_errors(document: Any, schema: dict[str, Any] | None = None) -> list[str]:
    errors = schema_errors(document, schema)
    if errors or not isinstance(document, dict):
        return errors
    return semantic_errors(document)


def validate_document(document: Any, schema: dict[str, Any] | None = None) -> None:
    errors = validation_errors(document, schema)
    if errors:
        raise DocumentValidationError("\n".join(errors))


def validate_examples(schema: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path in sorted((EXAMPLES_DIR / "valid").glob("*.json")):
        errors = validation_errors(load_json(path), schema)
        if errors:
            failures.append(f"expected valid: {path.name}: {'; '.join(errors)}")
    for path in sorted((EXAMPLES_DIR / "invalid").glob("*.json")):
        errors = validation_errors(load_json(path), schema)
        if not errors:
            failures.append(f"expected invalid: {path.name}")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Gate A v1 schema documents")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("schema", help="validate the JSON Schema itself")
    instance = subparsers.add_parser("instance", help="validate one JSON document")
    instance.add_argument("path", type=Path)
    subparsers.add_parser("examples", help="validate all valid and invalid example fixtures")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        schema = load_schema()
        if args.command == "schema":
            print(f"VALID schema {SCHEMA_PATH}")
            return 0
        if args.command == "instance":
            errors = validation_errors(load_json(args.path), schema)
            if errors:
                for error in errors:
                    print(f"INVALID {error}", file=sys.stderr)
                return 5
            print(f"VALID instance {args.path}")
            return 0
        failures = validate_examples(schema)
        if failures:
            for failure in failures:
                print(f"INVALID {failure}", file=sys.stderr)
            return 5
        print("VALID examples")
        return 0
    except (OSError, json.JSONDecodeError, TypeError) as error:
        print(f"VALIDATOR_ERROR {error}", file=sys.stderr)
        return 4
    except Exception as error:  # jsonschema schema errors and unexpected tool failures
        print(f"VALIDATOR_ERROR {type(error).__name__}: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
