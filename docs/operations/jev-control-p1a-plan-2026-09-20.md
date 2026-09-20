# P1a: dynamic obstacle and return to goal — experiment plan

Issue: [#39](https://github.com/blancaile/minecraft-ai/issues/39), parent [#37](https://github.com/blancaile/minecraft-ai/issues/37).
User authorized implementation and real-Jev evaluation on 2026-09-20. Experiments run on isolated loopback Paper, not shared terrain.

## Hypothesis and boundaries

P0 trace `8afb134e-e012-49df-8004-002e875f9ccb` shows eventual wall clearance followed by repeated STRAFE_LEFT despite a negative `goal_left_blocks`. The body faithfully moved +x, away from the goal. This is evidence of the selected correction being wrong, not proof of a memory deficit or a physical fault.

First intervention: expose the opposite signed projections `goal_back_blocks` and `goal_right_blocks` next to the existing forward/left projections, with an explicit coordinate definition. No action is ranked, removed, selected, or executed by this transform. The prompt, candidate list, physical inputs and observation visibility stay the same. Additional changes, if warranted by development failures, require a recorded hypothesis and separate artifact before another development batch.

## Fixed conditions

Paper 1.21.11 build 116, Java 21, Jev `jev-1.13.0`. Floor x/z -63..63 at y=80. Start `(0.5,81,0.5)`, goal `(0.5,81,20.5)`, radius 1. All runs start without a wall; the fixture adds it after observing at least three completed inputs and records actual timing.

| Preset | Initial yaw | Inclusive wall block bounds |
|---|---:|---|
| original-wall | 0 | (-1,81,4) .. (1,83,4) |
| mirrored-wall | 0 | (-2,81,4) .. (0,83,4) |
| initial-yaw | 90 | (-1,81,4) .. (1,83,4) |

The original course is symmetric about x=0.5. Reflecting the entire course about that axis would duplicate it. Therefore the second condition reflects the **wall volumes about world x=0 while retaining start and goal**: a block x maps to -x-1. This creates unequal left/right clearance and a distinct layout. It is not a full mirrored world or a guarantee of unseen-layout generalization. Preset names and intervention commands are never sent as policy inputs.

Each episode: maximum 60 decisions, 120 seconds, API timeout 10 seconds, snapshot age limit 200 ticks, 4-tick inputs, observation radius 3, distance bound 64. Same budget for baseline and changed variants. No mid-run changes, fallback, or API retries.

## Allocation and evaluation

- Baseline: 3 conditions × 3 runs = 9 episodes with the preserved P0 JAR, SHA-256 `165fd5ba4ac7ec9235e8019d3e283d56b97a6d8b4b1b32d57100b95b41c69344`.
- Development: at most 12 episodes total; version, hypothesis, preset and budget recorded before each batch.
- Final: 3 conditions × 3 runs = 9 episodes with one fixed final JAR and policy representation. Each condition must reach the goal at least twice, with evidence of wall observation and subsequent Jev-selected execution.
- If multiple interventions are combined: at most 3 additional ablation episodes to isolate the main addition, under the same budget. A single isolated change uses P0 as its ablation.
- Total ceiling: 33 live episodes / 1,980 decisions / 66 minutes of episode wall budgets. Startup/build/offline checks are separate. This is a ceiling, not a target. Stop a batch on API/observation/execution ERROR; preserve all evidence and investigate before any new explicitly recorded batch.

Development results are not counted as final acceptance. A failed final batch remains failed. Record actual goal-distance trajectories, collision/stagnation, action reversals, finite input correspondence, latency, candidate counts, terminal status and cleanup. Audit final results independently from raw traces and saved plan; success strings alone are insufficient. P0 and historical evidence are never rewritten.

Meeting 2/3 per condition is a small engineering criterion, not a statistical success-rate guarantee, P1-wide completion, general navigation, Gate A, or dragon capability.

## Allocation amendment before final evaluation

After the original 12 development episodes, variant 4 showed repeated WAIT despite lateral sweeps having no observed collision or unknown space in their two-block horizon. These were encoded as null distances. Reallocate the three reserved ablation episodes to a one-factor comparison: add the numerically explicit observed-clear distance (minimum of horizon, observed-contact distance and UNKNOWN distance). This adds no action preference. Variant 4 supplies the feature-removal comparison. Baseline remains 9, development/comparison becomes 15, final remains 9, and the total ceiling remains 33 episodes / 1,980 decisions. Conditions, per-run budgets and final pass criteria are unchanged. This amendment precedes all three added calls and the untouched final evaluation.
