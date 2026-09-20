"""Bounded, evidence-first P1a obstacle evaluation for the Paper Jev body.

Planning is side-effect free.  ``--execute`` is the only mode that reads a
credential or starts Paper; its evidence directory is newly allocated before
the key is read.  This module deliberately makes no claim about Gate A.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SERVER_SHA256 = "e708e8c132dc143ffd73528cccb9532e2eb17628b1a0eee74469bf466c7003f8"
CONFIG: dict[str, Any] = {
    "apiKey": "env:JEV_API_KEY", "model": "jev-1.13.0", "actionTicks": 4,
    "timeoutSeconds": 10, "maxObservationAgeTicks": 200, "maxDecisions": 60,
    "maxRunSeconds": 120, "observationRadius": 3, "goalRadius": 1.0,
    "maxDistanceFromSpawn": 64.0,
}
PUBLIC_CONFIG = {key: value for key, value in CONFIG.items() if key != "apiKey"}
WALL_ORIGINAL = [[-1, 81, 4], [1, 83, 4]]
# These conditions intentionally hold spawn/goal fixed.  "mirrored" describes
# the occupied wall volume, not an independent symmetric course.
PRESETS: dict[str, dict[str, Any]] = {
    "original-wall": {"yaw": 0, "goal": [.5, 81, 20.5], "wall": WALL_ORIGINAL},
    "mirrored-wall": {"yaw": 0, "goal": [.5, 81, 20.5], "wall": [[-2, 81, 4], [0, 83, 4]]},
    "initial-yaw": {"yaw": 90, "goal": [.5, 81, 20.5], "wall": WALL_ORIGINAL},
}
PHASES = ("baseline", "development", "final")
CRITERIA = {"final_runs_per_preset": 3, "final_min_arrivals_per_preset": 2,
            "wall_observation_decision_execution_required": True, "actual_goal_distance_required": True}
P0_ARTIFACT_SHA256 = "165fd5ba4ac7ec9235e8019d3e283d56b97a6d8b4b1b32d57100b95b41c69344"


def validate_plan(plan: dict[str, Any]) -> None:
    presets = plan.get("presets", [])
    if plan.get("phase") not in PHASES or not presets or len(presets) != len(set(presets)):
        raise EvidenceError("invalid phase or empty/duplicate presets")
    if any(name not in PRESETS for name in presets) or plan.get("preset_definitions") != {name: PRESETS[name] for name in presets}:
        raise EvidenceError("preset geometry, goal or yaw differs from fixed conditions")
    if plan.get("criteria") != CRITERIA or type(plan.get("repeats")) is not int or plan["repeats"] < 1:
        raise EvidenceError("invalid fixed criteria or repeats")
    if plan["phase"] in ("baseline", "final") and (presets != list(PRESETS) or plan["repeats"] != 3):
        raise EvidenceError("baseline/final requires exactly three fixed presets times three repeats")
    if plan["phase"] == "baseline" and plan.get("artifact_sha256") != P0_ARTIFACT_SHA256:
        raise EvidenceError("baseline artifact differs from the declared P0 JAR")


class EvidenceError(AssertionError):
    """Evidence is incomplete, contradictory, or cannot prove the predicate."""


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _command_output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=REPO, text=True).strip()


def _source_provenance() -> dict[str, str]:
    return {
        "source_commit": _command_output(["git", "rev-parse", "HEAD"]),
        "source_tree_sha256": _command_output(["git", "rev-parse", "HEAD^{tree}"]),
        "tracked_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=REPO)
        ).hexdigest(),
    }


def events(path: Path) -> list[dict[str, Any]]:
    """Read only newline-complete JSONL records; a partial final record is invalid."""
    raw = path.read_text(encoding="utf-8")
    if raw and not raw.endswith("\n"):
        raise EvidenceError("trace ends with a partial JSONL record")
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line]
    except json.JSONDecodeError as exc:
        raise EvidenceError("trace contains invalid JSON") from exc
    if not rows:
        raise EvidenceError("trace is empty")
    return rows


def _position(data: dict[str, Any]) -> list[float]:
    position = data.get("position")
    if not isinstance(position, list) or len(position) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in position):
        raise EvidenceError("invalid physical position")
    return [float(x) for x in position]


def verify_policy_encoding(observation: dict[str, Any]) -> None:
    if "policy_state" not in observation:
        return  # P0 and variants 1/2 transmitted the raw observation.
    if observation["policy_state"].get("policy_encoding") == "jev-task-facts-v1":
        selected = ("schema_version", "observation_id", "server_tick", "action_ticks", "self", "goal", "control_frame", "previous",
                    "legal_candidates", "excluded_candidates", "observed_body_sweeps", "visible_entities")
        expected = {key: observation[key] for key in selected if key in observation}
        feet = observation["self"]["position"][1]
        expected.update(policy_encoding="jev-task-facts-v1",
                        terrain_note="Only OBSERVED solid geometry above the feet is listed. Omitted cells are unrepresented, NOT empty. Four body sweeps separately report observed contact and UNKNOWN distances; no jump or route prediction. Support is measured by self.on_ground.",
                        observed_obstacles=[cell for cell in observation["local_cells"] if cell["knowledge"] == "OBSERVED" and any(cell["position"][1] + box[4] > feet + 1e-8 for box in cell["local_collision_boxes"])])
        if "control_frame" in observation:
            frame = observation["control_frame"]
            forward, left = frame["goal_forward_blocks"], frame["goal_left_blocks"]
            expected["goal_direction_description"] = f"Goal displacement relative to your current facing: {abs(forward):.3f} blocks {'FORWARD' if forward >= 0 else 'BACK'}; {abs(left):.3f} blocks to your {'LEFT' if left >= 0 else 'RIGHT'}. This states location, not a route."
        previous = observation.get("previous", {})
        if "goal" in observation and "after" in previous:
            after, delta = previous["after"]["position"], previous["displacement"]
            goal = observation["goal"]["position"]
            measured = math.dist(goal, after) - math.dist(goal, [after[i] - delta[i] for i in range(3)])
            actual = observation["policy_state"].get("last_input_goal_distance_change_blocks")
            if not isinstance(actual, (int, float)) or not math.isclose(actual, measured, abs_tol=1e-9):
                raise EvidenceError("policy distance change is not measured from previous input")
            expected["last_input_goal_distance_change_blocks"] = actual
        if observation["policy_state"] != expected:
            raise EvidenceError("policy task facts differ from observed geometry, goal or candidates")
        return
    expected = {key: value for key, value in observation.items() if key not in ("policy_state", "local_cells")}
    observed, unknown = [], []
    for cell in observation["local_cells"]:
        if cell["knowledge"] == "OBSERVED":
            observed.append(cell["position"] + [cell["block"], cell["fluid"], cell["local_collision_boxes"], cell["observed_tick"]])
        else:
            unknown.append(cell["position"] + [cell["unknown_reason"]])
    expected.update(policy_encoding="jev-cell-tables-v1",
                    observed_cell_columns="world_x,world_y,world_z,block,fluid,local_collision_boxes,observed_tick; every row is OBSERVED",
                    unknown_cell_columns="world_x,world_y,world_z,unknown_reason; every row is UNKNOWN, not empty space; unlisted cells are also UNKNOWN",
                    observed_cells=observed, unknown_cells=unknown)
    if observation["policy_state"] != expected:
        raise EvidenceError("policy state changed observed facts, unknown space, or legal candidates")


def _metrics(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    distances = [cycle["goal_distance"] for cycle in cycles]
    deltas = [distances[i + 1] - distances[i] for i in range(len(distances) - 1)]
    max_stagnation = current = 0
    for delta in deltas:
        if abs(delta) <= 0.02:
            current += 1
            max_stagnation = max(max_stagnation, current)
        else:
            current = 0
    reversals = 0
    for before, after in zip(cycles, cycles[1:]):
        left, right = before["horizontal_displacement"], after["horizontal_displacement"]
        if left[0] * right[0] + left[1] * right[1] < -0.01:
            reversals += 1
    return {
        "goal_distance_per_cycle": distances,
        "non_progress_cycles": sum(delta >= -0.02 for delta in deltas),
        "max_stagnation_streak": max_stagnation,
        "horizontal_direction_reversals": reversals,
    }


def summarize(path: Path) -> dict[str, Any]:
    """Verify P0's finite trace chain, then derive only from actual results."""
    rows = events(path)
    if rows[0].get("event") != "run_started" or rows[-1].get("event") != "terminal":
        raise EvidenceError("trace lacks run_started or terminal")
    meta, terminal, terminal_tick = rows[0]["data"], rows[-1]["data"], rows[-1].get("server_tick")
    if not isinstance(terminal_tick, int):
        raise EvidenceError("terminal lacks server tick")
    config = meta.get("config", {})
    required = ("actionTicks", "maxObservationAgeTicks", "goalRadius", "maxDecisions", "maxRunSeconds", "model")
    if any(key not in config for key in required):
        raise EvidenceError("trace lacks fixed P1 configuration")
    goal = _position({"position": meta.get("goal")})
    spawn = _position({"position": meta.get("spawn")})
    run_id = meta.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise EvidenceError("trace lacks run identifier")
    observation_rows = [row for row in rows if row.get("event") == "observation"]
    for observation_row in observation_rows:
        verify_policy_encoding(observation_row["data"])
    decisions = [row for row in rows if row.get("event") == "decision"]
    input_rows = [row for row in rows if row.get("event") == "input"]
    result_rows = [row for row in rows if row.get("event") == "result"]
    observation_ids = [row["data"].get("observation_id") for row in observation_rows]
    input_ids = [row["data"].get("request_id") for row in input_rows]
    result_ids = [row["data"].get("request_id") for row in result_rows]
    ids = [row["data"].get("request_id") for row in decisions]
    if (not ids or any(value is None for value in observation_ids + input_ids + result_ids + ids)
            or len(ids) != len(set(ids)) or len(observation_ids) != len(set(observation_ids))
            or len(input_ids) != len(set(input_ids)) or len(result_ids) != len(set(result_ids))
            or not set(ids).issubset(observation_ids) or set(ids) != set(input_ids) or set(ids) != set(result_ids)):
        raise EvidenceError("decision/input/result identifiers do not form one-to-one cycles")
    pending_observations = [row for row in observation_rows if row["data"]["observation_id"] not in ids]
    if len(pending_observations) > 1 or any(row["server_tick"] < result_rows[-1]["server_tick"] for row in pending_observations):
        raise EvidenceError("unbound observation is not the final pending request")
    observations = dict(zip(observation_ids, observation_rows))
    inputs = dict(zip(input_ids, input_rows))
    results = dict(zip(result_ids, result_rows))
    if len(ids) > config["maxDecisions"]:
        raise EvidenceError("trace exceeded fixed decision budget")
    first_observation = observation_rows[0]
    initial_self = first_observation["data"].get("self", {})
    initial_position = _position(initial_self)
    initial_yaw = initial_self.get("yaw")
    if not isinstance(initial_yaw, (int, float)) or not math.isfinite(initial_yaw):
        raise EvidenceError("first observation lacks finite yaw")
    cycles: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    latencies: list[float] = []
    ages: list[int] = []
    for decision in decisions:
        request_id = decision["data"]["request_id"]
        observation, input_row, result = observations.get(request_id), inputs[request_id], results[request_id]
        if observation is None:
            raise EvidenceError("decision is not bound to an observation")
        choice = decision["data"].get("response", {}).get("choice")
        if choice not in observation["data"].get("legal_candidates", []):
            raise EvidenceError("Jev selected a non-legal action")
        if input_row["data"].get("source") != "JEV" or input_row["data"].get("action") != choice or result["data"].get("action") != choice:
            raise EvidenceError("chosen action does not bind to Jev input and actual result")
        if not (observation["server_tick"] < decision["server_tick"] == input_row["server_tick"] < result["server_tick"]):
            raise EvidenceError("cycle tick order is invalid")
        if result["server_tick"] - input_row["server_tick"] != result["data"].get("actual_ticks") or result["data"].get("actual_ticks") != config["actionTicks"]:
            raise EvidenceError("actual action duration does not equal fixed configuration")
        if previous is not None:
            if observation["server_tick"] < previous["server_tick"] or observation["data"].get("previous") != previous["data"]:
                raise EvidenceError("observation does not bind to prior actual result")
        previous = result
        age = decision["server_tick"] - observation["server_tick"]
        if age > config["maxObservationAgeTicks"]:
            raise EvidenceError("stale observation accepted")
        before, after = _position(input_row["data"].get("before", {})), _position(result["data"].get("after", {}))
        displacement = result["data"].get("displacement")
        if not isinstance(displacement, list) or len(displacement) != 3 or any(not isinstance(value, (int, float)) for value in displacement):
            raise EvidenceError("invalid actual displacement")
        if any(abs((after[index] - before[index]) - displacement[index]) > 1e-8 for index in range(3)):
            raise EvidenceError("reported displacement contradicts actual positions")
        turn = (result["data"]["after"].get("yaw", 0) - input_row["data"]["before"].get("yaw", 0) + 180) % 360 - 180
        expected_turn = {"TURN_LEFT": -15, "TURN_RIGHT": 15}.get(choice, 0)
        if abs(turn - expected_turn) >= .01:
            raise EvidenceError("actual yaw contradicts action")
        cycle = {
            "request_id": request_id, "observation_tick": observation["server_tick"], "decision_tick": decision["server_tick"],
            "result_tick": result["server_tick"], "action": choice, "displacement": [float(value) for value in displacement],
            "horizontal_displacement": [float(displacement[0]), float(displacement[2])],
            "goal_distance": math.dist(after, goal), "latency_ms": decision["data"].get("latency_ms"), "snapshot_age_ticks": age,
        }
        cycles.append(cycle)
        latency = cycle["latency_ms"]
        if isinstance(latency, (int, float)) and math.isfinite(latency):
            latencies.append(float(latency))
        ages.append(age)
    final = _position(terminal.get("final", {}))
    elapsed_ms = terminal.get("elapsed_ms")
    decisions_reported = terminal.get("decisions")
    if not isinstance(elapsed_ms, int) or elapsed_ms < 0 or (terminal.get("status") == "GOAL_REACHED" and elapsed_ms > config["maxRunSeconds"] * 1000):
        raise EvidenceError("terminal elapsed time exceeds fixed wall budget")
    if decisions_reported != len(ids):
        raise EvidenceError("terminal decision count contradicts decision trace")
    if terminal.get("status") == "GOAL_REACHED" and math.dist(final, goal) > config["goalRadius"]:
        raise EvidenceError("goal terminal lacks actual arrival")
    last_result = result_rows[-1]
    final_tick_gap = terminal_tick - last_result["server_tick"]
    if final_tick_gap < 0 or (terminal.get("status") == "GOAL_REACHED" and final_tick_gap > config["maxObservationAgeTicks"]):
        raise EvidenceError("goal terminal is too distant from the last actual result")
    last_actual = _position(last_result["data"].get("after", {}))
    if final_tick_gap == 0:
        allowed_final_drift = 1e-8
    else:
        velocity = last_result["data"].get("after", {}).get("velocity")
        if not isinstance(velocity, list) or len(velocity) != 3 or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in velocity):
            raise EvidenceError("terminal inertia lacks an actual finite velocity")
        if terminal.get("status") == "GOAL_REACHED" and math.hypot(velocity[0], velocity[2]) > .5:
            raise EvidenceError("released velocity exceeds conservative bounded walking-body speed")
        # In this flat stone fixture no force accelerates a released body horizontally.
        # Air drag .91 is a conservative upper bound (stone ground friction is stronger).
        # Sum the decaying measured velocity, not an arbitrary terminal-only position.
        horizontal_bound = math.hypot(velocity[0], velocity[2]) * (1 - .91 ** final_tick_gap) / (1 - .91) + .01
        if terminal.get("status") == "GOAL_REACHED":
            for axis in (0, 2):
                drift = final[axis] - last_actual[axis]
                component_bound = abs(velocity[axis]) * (1 - .91 ** final_tick_gap) / (1 - .91) + .01
                if abs(drift) > component_bound or (abs(drift) > .01 and drift * velocity[axis] < 0):
                    raise EvidenceError("terminal drift contradicts released velocity direction")
        vertical_bound = abs(velocity[1]) * final_tick_gap + .08 * final_tick_gap * (final_tick_gap + 1) / 2 + .01
        if last_result["data"]["after"].get("on_ground"):
            vertical_bound = .01
        if terminal.get("status") == "GOAL_REACHED" and (math.hypot(final[0] - last_actual[0], final[2] - last_actual[2]) > horizontal_bound or abs(final[1] - last_actual[1]) > vertical_bound):
            raise EvidenceError("goal terminal exceeds released-body inertia envelope")
        allowed_final_drift = math.hypot(horizontal_bound, vertical_bound)
    final_drift = math.dist(final, last_actual)
    if terminal.get("status") == "GOAL_REACHED" and final_drift > allowed_final_drift:
        raise EvidenceError("goal terminal is not physically linked to the last actual result")
    return {
        "trace": path.name, "run_id": run_id, "policy": meta.get("policy"), "fault_fixture": meta.get("fault_fixture"),
        "artifact_sha256": meta.get("artifact_sha256"), "config": config,
        "spawn": spawn, "initial_position": initial_position, "initial_yaw": float(initial_yaw), "goal": goal,
        "cycles": cycles, "cycle_count": len(cycles), "status": terminal.get("status"), "reason": terminal.get("reason"),
        "final_position": final, "final_goal_distance": math.dist(final, goal), "final_result_tick_gap": final_tick_gap,
        "final_physical_drift": final_drift, "final_drift_bound": allowed_final_drift, "latency_ms": latencies,
        "snapshot_age_ticks": ages, "actions": dict(Counter(cycle["action"] for cycle in cycles)),
        "metrics": _metrics(cycles), "max_tick_gap_ms": terminal.get("max_tick_gap_ms"),
    }


def wall_evidence(path: Path, intervention: dict[str, Any]) -> dict[str, Any]:
    """Prove wall observation -> Jev choice -> input -> actual result, without inferring cause."""
    rows = events(path)
    if intervention.get("kind") != "wall" or not isinstance(intervention.get("after_tick"), int):
        raise EvidenceError("invalid intervention metadata")
    wall = intervention.get("wall")
    if wall not in [PRESETS[name]["wall"] for name in PRESETS]:
        raise EvidenceError("unrecognized wall geometry")
    if intervention.get("after_completed_cycles", 0) < 3:
        raise EvidenceError("wall was not placed after three completed cycles")
    if sum(row.get("event") == "result" and row.get("server_tick", -1) <= intervention["after_tick"] for row in rows) < 3:
        raise EvidenceError("wall timing is not supported by actual completed cycles")
    observations = [row for row in rows if row.get("event") == "observation" and row["server_tick"] > intervention["after_tick"]]
    decisions = {row["data"].get("request_id"): row for row in rows if row.get("event") == "decision"}
    inputs = {row["data"].get("request_id"): row for row in rows if row.get("event") == "input"}
    results = {row["data"].get("request_id"): row for row in rows if row.get("event") == "result"}
    low, high = wall
    observed: list[dict[str, Any]] = []
    for observation in observations:
        cells = observation["data"].get("local_cells", [])
        seen = any(cell.get("knowledge") == "OBSERVED" and cell.get("block") == "minecraft:stone" and low[0] <= cell.get("position", [None])[0] <= high[0]
                   and low[1] <= cell.get("position", [None, None])[1] <= high[1] and cell.get("position", [None, None, None])[2] == low[2]
                   for cell in cells)
        request_id = observation["data"].get("observation_id")
        if seen and request_id in decisions and request_id in inputs and request_id in results:
            observed.append({"request_id": request_id, "observation_tick": observation["server_tick"],
                             "decision_tick": decisions[request_id]["server_tick"], "result_tick": results[request_id]["server_tick"],
                             "action": decisions[request_id]["data"].get("response", {}).get("choice"),
                             "displacement": results[request_id]["data"].get("displacement")})
    if not observed:
        raise EvidenceError("no actual execution follows a wall-observing observation")
    return {"wall_observed_and_executed": True, "cycles": observed,
            "interpretation": "records observation/action/execution linkage; it does not assign a causal model capability"}


def _run_assessment(summary: dict[str, Any], intervention: dict[str, Any]) -> dict[str, Any]:
    assessment = dict(summary)
    try:
        assessment["wall_evidence"] = wall_evidence(Path(summary["trace_path"]), intervention)
        assessment["wall_execution"] = True
    except EvidenceError as exc:
        assessment["wall_execution"] = False
        assessment["wall_evidence_error"] = str(exc)
    assessment["arrival"] = summary["status"] == "GOAL_REACHED" and summary["final_goal_distance"] <= summary["config"]["goalRadius"]
    return assessment


# Reuse the pinned Paper process and receipt implementation used by P0.
from paper_acceptance import Server, events as live_events


def _plan(args: argparse.Namespace, artifact_sha256: str | None) -> dict[str, Any]:
    selected = [args.preset] if args.preset else list(PRESETS)
    if args.phase == "final" and args.preset:
        raise ValueError("final phase always evaluates all three fixed presets")
    if args.phase != "development" and args.preset:
        raise ValueError("--preset is allowed only for development")
    if args.repeats < 1: raise ValueError("--repeats must be positive")
    if args.phase == "final" and args.repeats != 3:
        raise ValueError("final phase requires exactly --repeats 3")
    plan = {
        "format": "p1a-acceptance-v1", "phase": args.phase, "repeats": args.repeats, "presets": selected,
        "spawn": [.5, 81, .5],
        "preset_definitions": {name: PRESETS[name] for name in selected}, "config": dict(PUBLIC_CONFIG),
        "credential_binding": "JEV_API_KEY supplied only to child process; never persisted",
        "intervention": {"kind": "wall", "after_completed_cycles_at_least": 3, "once_per_run": True},
        "criteria": dict(CRITERIA),
        "artifact_sha256": artifact_sha256, "server_sha256": SERVER_SHA256,
        "harness_sha256": _sha256(Path(__file__).resolve()), **_source_provenance(),
    }
    if args.artifact is not None:
        plan["artifact_filename"] = args.artifact.name
    validate_plan(plan)
    return plan


def _wait_for_terminal(server: Server, trace: Path, preset: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    intervention: dict[str, Any] | None = None
    deadline = time.monotonic() + CONFIG["maxRunSeconds"] + 5
    while time.monotonic() < deadline:
        rows = live_events(trace)
        if not rows: continue
        if rows[-1].get("event") == "terminal": break
        completed = sum(row.get("event") == "result" for row in rows)
        if intervention is None and completed >= 3:
            low, high = preset["wall"]
            server.send(f"fill {low[0]} {low[1]} {low[2]} {high[0]} {high[1]} {high[2]} minecraft:stone")
            server.wait("Successfully filled")
            intervention = {"kind": "wall", "wall": preset["wall"], "after_tick": rows[-1]["server_tick"],
                            "after_completed_cycles": completed, "placed_at_monotonic_ns": time.monotonic_ns()}
            _json(evidence_root / (trace.stem + "-intervention.json"), intervention)
        time.sleep(.03)
    else: raise TimeoutError("run exceeded declared 120-second budget")
    if intervention is None: # Valid failure evidence: no fabricated wall claim.
        intervention = {"kind": "wall", "wall": preset["wall"], "not_placed_reason": "fewer than three completed cycles"}
        _json(evidence_root / (trace.stem + "-intervention.json"), intervention)
    return intervention


def _final_verdict(runs: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("presets") != list(PRESETS) or plan.get("repeats") != 3:
        return {"passed": False, "per_preset": {}}
    grouped = {name: [run for run in runs if run.get("preset") == name] for name in plan["presets"]}
    details: dict[str, Any] = {}
    all_pass = True
    for name, values in grouped.items():
        arrivals = sum(value.get("arrival") for value in values)
        wall_execution = all(value.get("wall_execution") for value in values)
        exact_count = len(values) == 3
        passed = exact_count and arrivals >= 2 and wall_execution
        details[name] = {"runs": len(values), "arrivals": arrivals, "wall_execution_all_runs": wall_execution, "passed": passed}
        all_pass = all_pass and passed
    return {"passed": all_pass, "per_preset": details}


def execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    if args.artifact is None or args.key_file is None:
        raise ValueError("--artifact and --key-file are required with --execute")
    if not args.artifact.is_file(): raise FileNotFoundError("artifact does not exist")
    root = REPO / ".runtime-harness" / ("p1a-" + args.phase + "-" + uuid.uuid4().hex[:12])
    root.mkdir(parents=True, exist_ok=False); _json(root / "plan.json", plan)
    # The Git diff does not include untracked files.  Bind the exact evaluator
    # source and retain a readable copy beside the raw trace for offline audit.
    evaluator = Path(__file__).resolve()
    shutil.copy2(evaluator, root / "p1_acceptance.py")
    helper = Path(__file__).with_name("paper_acceptance.py")
    shutil.copy2(helper, root / "paper_acceptance.py")
    plan["paper_acceptance_sha256"] = _sha256(helper)
    _json(root / "plan.json", plan)
    print("EVIDENCE_DIRECTORY=" + str(root), flush=True)
    # Import only in execute mode so planning/auditing never touches credential storage.
    sys.path.insert(0, str(REPO / "tools/probes"))
    from jev_client import load_jev_api_key
    environment = os.environ.copy(); environment.pop("JEV_API_KEY", None)
    environment["JEV_API_KEY"] = load_jev_api_key(args.key_file)
    server: Server | None = None
    bot_may_exist = False
    report: dict[str, Any] = {"format": "p1a-report-v1", "phase": args.phase, "status": "RUNNING", "plan_sha256": _sha256(root / "plan.json"),
                              "artifact_sha256": plan["artifact_sha256"], "runs": [], "cleanup": {"verified_no_bot": False}}
    api_error = False
    try:
        server = Server(root, args.artifact, environment); environment.pop("JEV_API_KEY", None); server.setup()
        for preset_name in plan["presets"]:
            for repeat in range(plan["repeats"]):
                trace = server.prepare(PRESETS[preset_name], CONFIG)
                bot_may_exist = True
                intervention = _wait_for_terminal(server, trace, PRESETS[preset_name], root)
                try:
                    summary = summarize(trace); summary["trace_path"] = str(trace); summary["preset"] = preset_name; summary["repeat"] = repeat + 1
                    assessment = _run_assessment(summary, intervention); assessment.pop("trace_path", None)
                    assessment["valid_trace"] = True
                except EvidenceError:
                    # Keep a timeout/interrupted raw trace as a failed run.  It
                    # must never become an arrival through missing evidence.
                    terminal = events(trace)[-1].get("data", {})
                    assessment = {"trace": trace.name, "run_id": events(trace)[0].get("data", {}).get("run_id"), "preset": preset_name, "repeat": repeat + 1,
                                  "status": terminal.get("status", "UNVERIFIABLE"), "arrival": False,
                                  "wall_execution": False, "valid_trace": False, "verification_error": "invalid_or_partial_trace"}
                assessment["intervention_file"] = trace.stem + "-intervention.json"
                report["runs"].append(assessment)
                _json(root / "verification.json", report) # Keep every failed run before any later action.
                assessment["settled"] = server.release_check()
                receipt = server.command("jev despawn")
                assessment["despawn_receipt"] = receipt
                bot_may_exist = False
                print(json.dumps({"preset": preset_name, "repeat": repeat + 1, "status": assessment["status"], "cycles": assessment.get("cycle_count"), "distance": assessment.get("final_goal_distance"), "wall_execution": assessment.get("wall_execution")}), flush=True)
                if assessment["status"] == "ERROR": api_error = True; break
            if api_error: break
        phase_passed = all(run.get("arrival") and run.get("wall_execution") for run in report["runs"])
        report["final_criterion"] = _final_verdict(report["runs"], plan) if args.phase == "final" else None
        report["status"] = "PASSED" if (report["final_criterion"]["passed"] if args.phase == "final" else phase_passed) and not api_error else "COMPLETED_WITH_FAILURES"
    except BaseException as exc:
        report["status"] = "HARNESS_ERROR"; report["failure_type"] = type(exc).__name__
        # Never serialize exception text: callers/libraries could include a credential.
        raise
    finally:
        if server is not None:
            if bot_may_exist:
                # An exception between start and normal teardown must still ask
                # the owned plugin to stop and despawn this experiment's bot.
                emergency: dict[str, Any] = {}
                try: emergency["stop_receipt"] = server.command("jev stop")
                except Exception: emergency["stop_receipt"] = "unavailable"
                try:
                    emergency["despawn_receipt"] = server.command("jev despawn")
                    bot_may_exist = False
                except Exception: emergency["despawn_receipt"] = "unavailable"
                report["emergency_cleanup"] = emergency
            try:
                receipt = server.command("jev status")
                report["cleanup"] = {"status_receipt": receipt, "verified_no_bot": any("bot=none" in item for item in receipt.get("output", []))}
                if not report["cleanup"]["verified_no_bot"]: report["status"] = "COMPLETED_WITH_FAILURES"
            except Exception:
                report["cleanup"] = {"verified_no_bot": False, "status": "receipt_unavailable"}; report["status"] = "COMPLETED_WITH_FAILURES"
            server.close()
        _json(root / "verification.json", report)
        print("STATUS=" + report["status"], flush=True)
    return 0 if report["status"] == "PASSED" else (2 if args.phase == "final" else 0)


def audit_directory(directory: Path) -> dict[str, Any]:
    plan_path, report_path = directory / "plan.json", directory / "verification.json"
    if not plan_path.is_file() or not report_path.is_file(): raise EvidenceError("missing plan or report")
    plan, report = json.loads(plan_path.read_text(encoding="utf-8")), json.loads(report_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    if plan.get("format") != "p1a-acceptance-v1" or report.get("format") != "p1a-report-v1": raise EvidenceError("unknown P1a evidence format")
    if report.get("plan_sha256") != _sha256(plan_path): raise EvidenceError("report does not bind plan hash")
    if report.get("artifact_sha256") != plan.get("artifact_sha256") or not isinstance(plan.get("artifact_sha256"), str): raise EvidenceError("artifact hash mismatch")
    artifact_copy = directory / "plugins" / str(plan.get("artifact_filename", ""))
    if not artifact_copy.is_file() or _sha256(artifact_copy) != plan["artifact_sha256"]:
        raise EvidenceError("copied artifact is missing or hash-mismatched")
    config = plan.get("config")
    if config != PUBLIC_CONFIG: raise EvidenceError("P1a config drifted from fixed P0 configuration")
    expected_spawn = plan.get("spawn", [.5, 81, .5])
    if expected_spawn != [.5, 81, .5]: raise EvidenceError("P1a spawn drifted")
    evaluator_snapshot = directory / "p1_acceptance.py"
    if not evaluator_snapshot.is_file() or plan.get("harness_sha256") != _sha256(evaluator_snapshot):
        raise EvidenceError("evaluator source snapshot hash mismatch")
    helper_snapshot = directory / "paper_acceptance.py"
    if plan.get("paper_acceptance_sha256") is not None and (not helper_snapshot.is_file() or plan["paper_acceptance_sha256"] != _sha256(helper_snapshot)):
        raise EvidenceError("Paper helper source snapshot hash mismatch")
    reconstructed: list[dict[str, Any]] = []
    trace_dir = directory / "plugins/JevControl/traces"
    raw_traces: set[str] = set()
    raw_run_ids: set[str] = set()
    for candidate in trace_dir.glob("*.jsonl"):
        rows = events(candidate)
        if rows[0].get("event") == "run_started":
            run_id = rows[0].get("data", {}).get("run_id")
            if not isinstance(run_id, str) or not run_id or run_id in raw_run_ids:
                raise EvidenceError("duplicate or invalid raw run identifier")
            raw_run_ids.add(run_id); raw_traces.add(candidate.name)
    report_traces = [run.get("trace") for run in report.get("runs", [])]
    if len(report_traces) != len(set(report_traces)) or set(report_traces) != raw_traces:
        raise EvidenceError("reported traces do not enumerate every raw P1 run exactly once")
    run_ids: set[str] = set()
    repeats: set[tuple[str, Any]] = set()
    for run in report.get("runs", []):
        trace = trace_dir / run.get("trace", "")
        intervention_path = directory / run.get("intervention_file", "")
        if not trace.is_file() or not intervention_path.is_file(): raise EvidenceError("run lacks raw trace or intervention")
        intervention = json.loads(intervention_path.read_text(encoding="utf-8"))
        if run.get("preset") not in plan["presets"] or intervention.get("wall") != plan["preset_definitions"][run["preset"]]["wall"]:
            raise EvidenceError("run preset does not bind the planned wall geometry")
        repeat_key = (run["preset"], run.get("repeat"))
        if repeat_key in repeats or not isinstance(run.get("repeat"), int) or run["repeat"] < 1 or run["repeat"] > plan["repeats"]:
            raise EvidenceError("duplicate or invalid preset repeat")
        repeats.add(repeat_key)
        if run.get("valid_trace"):
            summary = summarize(trace)
            if summary["artifact_sha256"] != plan["artifact_sha256"] or summary["config"] != PUBLIC_CONFIG:
                raise EvidenceError("trace artifact/config mismatch")
            if summary["policy"] != "JEV" or summary["fault_fixture"] is not False:
                raise EvidenceError("live acceptance trace is not a real Jev policy run")
            preset = plan["preset_definitions"][run["preset"]]
            if summary["goal"] != preset["goal"] or summary["spawn"] != expected_spawn:
                raise EvidenceError("trace goal or spawn differs from plan")
            if math.dist(summary["initial_position"], expected_spawn) > .01 or abs((summary["initial_yaw"] - preset["yaw"] + 180) % 360 - 180) > .01:
                raise EvidenceError("first observation does not bind planned initial pose")
            if summary["run_id"] in run_ids or (run.get("run_id") is not None and run["run_id"] != summary["run_id"]):
                raise EvidenceError("duplicate or mismatched raw run identifier")
            run_ids.add(summary["run_id"])
            summary["trace_path"] = str(trace); summary["preset"] = run.get("preset"); summary["repeat"] = run.get("repeat")
            reconstructed.append(_run_assessment(summary, intervention))
        else:
            try: summarize(trace)
            except EvidenceError:
                trace_rows, terminal = events(trace), events(trace)[-1].get("data", {})
                run_id = trace_rows[0].get("data", {}).get("run_id")
                if run.get("run_id") != run_id or run_id in run_ids: raise EvidenceError("duplicate or mismatched raw run identifier")
                run_ids.add(run_id)
                reconstructed.append({"trace": trace.name, "run_id": run_id, "preset": run.get("preset"), "repeat": run.get("repeat"),
                                      "status": terminal.get("status", "UNVERIFIABLE"), "arrival": False,
                                      "wall_execution": False, "valid_trace": False})
            else: raise EvidenceError("report labels a valid trace unverifiable")
    if len(reconstructed) != len(report.get("runs", [])) or run_ids != raw_run_ids:
        raise EvidenceError("run reconstruction count or identifiers mismatch")
    expected = len(plan["presets"]) * plan["repeats"]
    if plan["phase"] == "final" and len(reconstructed) != expected: raise EvidenceError("final evidence lacks exact fixed run count")
    verdict = _final_verdict(reconstructed, plan) if plan["phase"] == "final" else None
    if plan["phase"] == "final" and report.get("final_criterion") != verdict: raise EvidenceError("reported final criterion is not reproducible")
    receipts = directory / "plugins/JevControl/receipts"
    raw_receipts = [] if not receipts.is_dir() else [json.loads(path.read_text(encoding="utf-8")) for path in receipts.glob("*.json")]
    receipt_by_id = {receipt.get("id"): receipt for receipt in raw_receipts if isinstance(receipt.get("id"), str)}
    if len(receipt_by_id) != len(raw_receipts): raise EvidenceError("duplicate or invalid raw receipt identifier")
    despawn_times: list[int] = []
    for run in report.get("runs", []):
        receipt = run.get("despawn_receipt")
        if not isinstance(receipt, dict) or receipt_by_id.get(receipt.get("id")) != receipt or not receipt.get("success"):
            raise EvidenceError("run despawn receipt is missing or does not bind raw receipt")
        completed = receipt.get("completed_at_ms")
        if not isinstance(completed, int): raise EvidenceError("run despawn receipt lacks completion time")
        despawn_times.append(completed)
    cleanup = report.get("cleanup", {})
    status_receipt = cleanup.get("status_receipt") if isinstance(cleanup, dict) else None
    if not isinstance(status_receipt, dict) or receipt_by_id.get(status_receipt.get("id")) != status_receipt:
        raise EvidenceError("cleanup status receipt is missing or does not bind raw receipt")
    completed = status_receipt.get("completed_at_ms")
    output = status_receipt.get("output", [])
    if (not status_receipt.get("success") or not isinstance(completed, int) or (despawn_times and completed < max(despawn_times))
            or not isinstance(output, list) or not any(isinstance(line, str) and "bot=none" in line for line in output)
            or not cleanup.get("verified_no_bot")):
        raise EvidenceError("cleanup status receipt does not prove bot absence after the final run")
    audit = {"format": "p1a-audit-v1", "status": ("PASSED" if verdict["passed"] else "FAILED") if verdict else "EVIDENCE_VALID",
             "reported_experiment_status": report.get("status"), "runs": reconstructed, "final_criterion": verdict}
    _json(directory / ("audit-" + uuid.uuid4().hex[:8] + ".json"), audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--phase", choices=PHASES, default="development")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--preset", choices=tuple(PRESETS))
    parser.add_argument("--audit-directory", type=Path)
    args = parser.parse_args()
    if args.audit_directory:
        if args.execute: parser.error("--audit-directory cannot be combined with --execute")
        audit = audit_directory(args.audit_directory)
        print(json.dumps({"status": audit["status"], "runs": len(audit["runs"]), "final_criterion": audit["final_criterion"]}, ensure_ascii=False))
        return 0 if audit["status"] in ("PASSED", "EVIDENCE_VALID") else 2
    artifact_sha256 = _sha256(args.artifact) if args.artifact and args.artifact.is_file() else None
    plan = _plan(args, artifact_sha256)
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2)); return 0
    if artifact_sha256 is None: raise FileNotFoundError("artifact does not exist")
    return execute(args, plan)


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (EvidenceError, ValueError, FileNotFoundError, TimeoutError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(4)
