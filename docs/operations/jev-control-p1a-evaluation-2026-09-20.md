# Issue #39: P1a evaluation (2026-09-20)

Status: implementation and evaluation in progress. No P1a pass claimed.
Predeclared conditions and budget: [experiment plan](jev-control-p1a-plan-2026-09-20.md).

## P0 failure diagnosis

Preserved trace: `.runtime-harness/paper-live-08cd855d4b68/plugins/JevControl/traces/8afb134e-e012-49df-8004-002e875f9ccb.jsonl`.

- FORWARD hit the new wall near z=3.70. Zero-displacement results and `horizontal_collision=true` exposed the failure to the next observation.
- Jev eventually moved sideways to x≈2.86 and then advanced past the wall toward z≈19.76. Avoidance was partially successful.
- At that point the goal's lateral displacement was approximately -2.36 blocks. At yaw 0, `STRAFE_LEFT` is +x and `STRAFE_RIGHT` is -x, as both the mechanical frame and actual displacements show.
- Jev repeatedly chose STRAFE_LEFT, increasing the lateral error. Every inspected observation for decisions 45–60 retained the negative `goal_left_blocks`; the right action remained legal. At decisions 45/50/57/60 the left/right probabilities were respectively .43/.28, .43/.28, .47/.21 and .38/.22.
- Input usage around these failures was approximately 11k tokens. The saved observations contain the relevant goal facts; they do not establish an API-side truncation defect.
- Terminal position was approximately `(18.059,81,20.843)`, followed by inertial settling near `(18.289,81,20.843)`. These are different sampling times, not conflicting results. Both miss the goal.

The directly supported defect is the selected direction after bypass, not absent action candidates or reversed physical execution. A semantic/sign interpretation failure is a hypothesis. A controller rule that silently chooses the corrective action would defeat the experiment.

## Development variant 1: symmetric goal projections

Add signed back/right projections to the existing forward/left projections and define their sign explicitly. This is the same linear coordinate transform, applied to all four input axes. No ranking, candidate filtering, preferred action, target waypoint or obstacle policy is produced. Prompt and physical control remain unchanged.

JAR SHA-256: `01e1b492da0cf7346480cb0f2af5c403e6e48ea3519307fd2835cb1ea0e95d7a`.
Checks: Java 19 tests, 7 deployment checks, 3 P0 evidence-verifier tests, 22 isolated Paper body checks passed. Body evidence: `.runtime-harness/paper-smoke-5a4ef145f9d3/verification.json`.

Baseline `.runtime-harness/p1a-baseline-461590695e26`: original 0/3, mirrored-wall 3/3 (25 decisions each), initial-yaw 0/3; 435 completed cycles. All failed runs exhausted 60 decisions, without runtime ERROR. Independent raw-trace audit reconstructed all nine runs. Evidence validity is distinct from task success.

Variant 1 development `.runtime-harness/p1a-development-84b7243af570`: original FAILED (60 decisions, distance 17.096), mirrored-wall reached (25), initial-yaw reached (34), 119 cycles. The original run remained around x=2.0,z=3.7, where the body's width still overlaps the wall edge. Symmetric goal projection alone was insufficient. All raw failures remain saved.

## Development variant 2: observed body-contact distances

Hypothesis: reading several hundred world-coordinate cells does not reliably expose the difference between the body center clearing a wall and the body's full width clearing it. Append four horizontal straight body sweeps derived only from the saved OBSERVED collision boxes. Report distance to observed contact and distance to UNKNOWN separately, over a 2-block horizon at current body height. Unlisted cells remain unknown. Use the actual body's width/height. These calculations do not simulate a path, predict jump success, remove actions, or choose which direction to take.

Keep variant 1 projections and the original prompt/candidates. The three variant 1 runs are the geometry-removal comparison; variant 2 uses another three development episodes (one per condition) from the original 12-episode development allocation. Final evaluation has not started.

Variant 2 JAR SHA-256: `f06d09fa8c24bec201cd931ac9627f5763c59b312fe32122b3a69dfb7dff3545`.

Variant 2 development `.runtime-harness/p1a-development-4e38ea89fa27`: original FAILED (60 decisions, distance 17.491), mirrored-wall reached (26), initial-yaw reached (43), 129 cycles. The original run still failed near the wall. Added geometry facts alone did not establish improvement; all three batches (baseline and development 1/2) pass evidence reconstruction, not P1a acceptance.

## Development variant 3: lossless compact cell tables

Hypothesis: the approximately 11k-token repeated per-cell object representation makes the useful goal/body geometry difficult to use. This is a representation hypothesis, not a finding of API truncation. Replace repeated cell keys in the policy request with explicitly described tables. Preserve every observed coordinate, block, fluid flag, collision box, observation tick and every unknown coordinate/reason. Preserve self, goal, prior result, legal/excluded candidates, control projections and body sweeps. Save both raw snapshot and the exact policy state in each observation trace. Do not change the prompt or choose an action in the encoder.

Variant 3 uses three development episodes (one per condition), bringing development allocation to 9/12. Variant 2 is the full-object encoding comparison. JAR SHA-256: `1131355d680b8e8b84279adaf04f9340c845b493db1424bb2d2cd240e52f63c6`.

Variant 3 `.runtime-harness/p1a-development-314d5cb57807`: all three runs FAILED at 60 decisions (distances 16.800, 16.800, 11.392), 180 cycles. Original/mirrored repeatedly alternated WAIT and blocked FORWARD. Input tokens fell to approximately 6k, but behavior worsened. This rejects token-count reduction alone as a sufficient fix in these trials.

## Development variant 4: compact task facts

Use the remaining three development episodes (12/12 total). Hypothesis: expose navigation-relevant observed facts directly with an explicit textual goal-location description, instead of requiring interpretation of large cell arrays. Preserve self, known goal, previous outcome, all legal/excluded candidates, mechanical control projections and body-contact sweeps. Include every OBSERVED collision cell above the feet, including its original shape and timestamp. Omitted terrain is explicitly unrepresented, not empty; sweeps retain UNKNOWN contact separately and the full raw cells remain in the trace. Describe the signed goal displacement in words (e.g. a location to the RIGHT) and measure the previous input's actual change in Euclidean goal distance. Neither field is an action recommendation or candidate score; temporary movement away remains legal. No dedicated wall-escape instructions, macro, waypoint or prompt change.

This representation intentionally selects task facts; it is **not** the lossless encoding of variant 3. Its information-selection contribution must be included when interpreting Jev's performance. The independent verifier reconstructs the full policy-state derivation from raw facts, including goal description, obstacle cells and unchanged candidates.

Variant 4 JAR SHA-256: `efb478b18de96536a3b2230b42d1fa759cfb56ee2b0c2b564981065bd08a300d`. `.runtime-harness/p1a-development-1c552322f0aa`: all three FAILED at 60 decisions (distances 16.800, 16.800, 16.801), 180 cycles. At yaw 0, lateral sweeps reported null collision/unknown distances within the horizon, yet WAIT was repeatedly favored. Input tokens were approximately 1.5k. Six isolated injected faults on this artifact passed in `.runtime-harness/paper-faults-b0ebe9d2ea75` (separate dummy policy, not real-Jev evidence).

## Development variant 5: explicit measured clear distance

Use the three comparison episodes reallocated in the plan before these calls. Add `observed_clear_distance_blocks` for all four body axes, the minimum of the two-block horizon, observed collision contact and UNKNOWN contact. A value of 2 states no contact in the measured horizon, while unknown space yields a bounded value, including zero. Preserve the original collision/unknown fields, all candidates, current task-facts representation and prompt. No direction is ranked or selected. This one-field intervention tests the null-versus-explicit-distance representation hypothesis against variant 4. Final evaluation will use one fixed artifact, with no tuning during its nine runs.

Variant 5 JAR SHA-256: `731b4cef4d8b6d3426af4b56507374aaa596c8a586e1e790a8c83c23c85838d3`. Java 24 tests, deployment checks 7, P0 verifier tests 3, P1 verifier tests 10 passed before its live comparison; Paper body checks are recorded in `.runtime-harness/paper-smoke-c92724753126`.
