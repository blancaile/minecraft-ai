# Gate A Contract v1.0

- Status: Frozen acceptance contract
- Date: 2026-09-19
- Issue: [GA-005](https://github.com/blancaile/minecraft-ai/issues/8)
- Supersedes: [Gate A Intent Contract](gate-a-intent.md) for measurement and acceptance
- Applies to: Minecraft body candidates, not Resident cognition

## 1. Gate decision

Gate A asks one question:

> Can the body execute deterministic survival missions, reach an externally verified terminal result after bounded recovery, respect authority boundaries, and remain observable across death and restart without human rescue?

Gate A is **not yet passed**. This document freezes what a future run must prove. Upstream unit tests, GameTests, capability claims, and self-generated evidence are diagnostic inputs only and never sufficient for a Gate A pass.

A candidate passes Gate A v1 only when:

1. every mandatory scenario meets its mission-level threshold;
2. no zero-tolerance failure occurs in any valid run;
3. the candidate-independent evidence bundle validates and is sealed;
4. no scenario is `BLOCKED` or lacks a valid required run;
5. the full suite is executed against one immutable candidate revision and one recorded effective configuration.

## 2. Basis and traceability

| Input | Contract consequence |
|---|---|
| [GA-001 Intent](gate-a-intent.md) | Nine capability requirements and unacceptable failure classes become mandatory assertions |
| [GA-000 audit](../discovery/mc-aiplayer-supply-chain-audit.md) | Immutable source/dependency provenance, secret-free execution, exact process targeting, and prohibited destructive scripts |
| [GA-002 reproduction](../discovery/pinned-baseline-results.md) | Upstream self-test is reproducible but is not independent evidence; Java 21 / Minecraft 1.21.3 is a viable reference environment |
| [GA-003 matrix](../discovery/body-candidate-matrix.md) | Independent controller/observer, natural navigation, mission chains, mutation audit, recovery, and evidence sealing are explicit gaps |
| [ADR-0001](../adr/0001-body-strategy.md) | No import/fork/port during DEFER; evaluate unchanged fixed SHA first and then choose one terminal strategy |

## 3. Normative terminology

### Run, attempt, recovery, and mission

- A **run** is one isolated fixture, candidate process set, mission command, observation stream, and terminal artifact.
- An **attempt** is a body-internal action toward the mission. Attempt success rate is not a Gate metric.
- A **recovery episode** starts when the body declares or the observer detects a failure condition and ends when forward mission progress resumes, the body enters a terminal state, or the recovery budget expires.
- A **mission** spans its initial attempt and all allowed recovery episodes. The harness does not restart a failed mission to turn it into a success.

### Mission terminal states

The candidate adapter must associate exactly one terminal state with the mission correlation ID:

- `COMPLETED`: candidate claims completion.
- `FAILED`: candidate stops with a machine-readable reason.
- `CANCELLED`: declared controller cancellation reached quiescence.
- `PARTIAL`: some work completed but the declared postcondition did not.

Harness-level states are separate:

- `PASS`: candidate terminal, external postcondition, budget, and safety assertions all agree.
- `FAIL`: valid run violates any candidate assertion.
- `BLOCKED`: a required observation/control surface cannot be supplied or a repeatable environment precondition is absent.
- `HARNESS_ERROR`: controller, observer, fixture, or artifact pipeline failed before a valid verdict could be produced.

`PARTIAL` is always a Gate failure. A `COMPLETED` claim without the external postcondition is `FAIL_FALSE_COMPLETION`. A postcondition reached without a correlated terminal report is `FAIL_UNOBSERVABLE_TERMINAL`; the harness must not silently synthesize success.

### Mission completion after bounded recovery

A mission passes only if, before its timeout:

1. the candidate emits `COMPLETED` for the correlation ID;
2. the independent observer confirms every positive and negative postcondition;
3. recovery count and cumulative recovery time are within the scenario budget;
4. no zero-tolerance event occurred;
5. state remains stable for a 5-second / 100-server-tick settle window after terminal, using the longer wall-clock duration.

### Progress and permanent stall

Progress is an externally observed change listed by the scenario, such as displacement along an accepted route, target inventory delta, required world-state delta, recovery-state transition, or an explicit bounded wait whose deadline is in the manifest. Logs, repeated commands, path recalculation, retry counters, animation, or candidate heartbeat alone are not progress.

A **permanent stall** occurs when the scenario's stall window expires without progress and without a declared bounded wait. The controller then captures diagnostics and terminates the mission as `FAIL_STALL`; further retries are not permitted.

### Human intervention

Human intervention is any post-start manual command, teleport, item grant, block/entity/inventory edit, process-state edit, task rewrite, or candidate-state repair not predeclared in the scenario's injection manifest. Observation without mutation is allowed.

Any human intervention makes the valid run `FAIL_HUMAN_INTERVENTION`; it is not a harness error and cannot be discarded. The test server rejects unregistered player connections during a run. Controller actions carry a correlation ID and are limited to the manifest.

### Unauthorized mutation

An unauthorized mutation is any block, entity, inventory, container, player, game-rule, permission, or process-relevant world change outside the scenario's actor/target/region/capability allowlist. A reverted mutation still fails. A mutation that cannot be attributed to the candidate, controller, vanilla environment, or named external actor is `FAIL_UNATTRIBUTED_MUTATION`.

## 4. Reference execution environment

The canonical v1 environment is:

| Item | Required value |
|---|---|
| Host | isolated Linux or WSL2 Linux filesystem; x86-64 |
| Java | JDK 21; vendor/release/package SHA-256 recorded |
| Minecraft | Java Edition dedicated server 1.21.3 |
| Fabric Loader | 0.18.4 |
| Fabric API | 0.114.1+1.21.3 |
| Game mode | survival |
| Difficulty | normal |
| Server auth | `online-mode=false` in the isolated non-public test network |
| Inventory rule | `keepInventory=false` |
| LLM | disabled; no Jev, DeepSeek, story, or open-ended planner |
| Privileged body capabilities | teleport, hidden world scan, forced pickup, direct world mutation, item grant all disabled |
| Time | wall time from a monotonic clock plus server tick recorded |
| Isolation | a fresh run directory and pristine fixture copy per run; no shared candidate runtime state |

If a candidate cannot operate in this environment, the result is `BLOCKED`, not a waived requirement. A later Gate version may add an online-mode deployment profile; v1 does not convert test account operations into body capability evidence.

Dependencies may be downloaded only before the run and must be checksum/lock verified. The run itself is secret-free. Destructive global commands, wildcard deletion, and global process-name kills are forbidden; the controller may stop only recorded PIDs/process groups under its run directory.

## 5. Independent harness boundary

The minimum Acceptance Harness has four trust-separated parts:

1. **External orchestrator** — creates the run directory, starts exact processes, issues declared commands/injections, enforces time, and seals artifacts.
2. **Independent observer** — records player/world/inventory/container/entity state and mutations without importing candidate packages or accepting candidate success as truth.
3. **Candidate adapter** — translates spawn/mission/cancel/status requests. It may record candidate output but may not implement assertions.
4. **Postcondition verifier** — consumes the contract, fixture manifest, observer stream, and snapshots to decide results.

The observer and verifier must build and test without the candidate source tree. Candidate-specific class names, internal task phases, log strings, or evidence validators may not be required for a PASS. Server-console privilege is permitted only to fixture setup and declared injection code; gameplay success must result from the body under survival constraints.

Canonical interface:

```text
gate-a validate-contract --contract gate-a-v1
gate-a run --candidate <manifest> --suite decision|full --output <new-directory>
gate-a verify --bundle <locked-directory> [--require-pass]
```

Exit codes:

| Code | Meaning |
|---:|---|
| `0` | requested operation valid; `run --suite full` uses 0 only for a full Gate PASS |
| `2` | candidate/scenario `FAIL` |
| `3` | `BLOCKED` |
| `4` | `HARNESS_ERROR` or invalid artifact |
| `5` | contract/config/provenance error before execution |

## 6. Global budgets and rerun policy

- Default mission timeout: 300 wall-clock seconds from acknowledged mission command through settle window.
- Default stall window: 30 wall-clock seconds.
- Default recovery budget: at most 2 episodes and at most 60 cumulative wall-clock seconds, whichever is reached first.
- The same normalized failure signature may trigger recovery at most once. Its second occurrence is terminal failure.
- Timeout includes candidate thinking, waiting, recovery, and action. Only GA-RST-01 has a separately declared server-down interval, still bounded by its total timeout.
- A candidate crash, disconnect, timeout, assertion failure, malformed terminal, or missing artifact is not rerunnable as infrastructure noise.
- `HARNESS_ERROR` may be rerun once from a fresh fixture only if artifacts show the candidate mission was never acknowledged or no trustworthy observation began. Both attempts remain in the aggregate. A repeated harness error makes the scenario `BLOCKED` and Gate A cannot pass.
- Seeds and fixture hashes are committed before candidate execution. Failed seeds are never replaced.

## 7. Mandatory scenarios

### Scenario matrix

| ID | Requirement | Valid runs | Mission timeout | Stall window | Recovery budget | Pass threshold |
|---|---|---:|---:|---:|---|---:|
| `GA-LIF-01` | lifecycle integrity | 3 | 60 s | 15 s | 0 | 3/3 |
| `GA-OBS-01` | observation integrity | 5 | 60 s | 15 s | 0 | 5/5 |
| `GA-CTL-01` | control/cancel safety | 3 | 90 s | 10 s after cancel | 0 after cancel | 3/3 |
| `GA-NAV-01` | natural navigation | 20 fixed seeds | 180 s | 30 s | 2 episodes / 60 s | at least 18/20 |
| `GA-NAV-02` | unreachable target | 3 | 45 s | 15 s | 1 episode / 15 s | 3/3 |
| `GA-RES-01` | acquire, carry, store | 20 fixed seeds | 300 s | 30 s | 3 episodes / 90 s | at least 18/20 |
| `GA-INT-01` | inventory, craft, smelt | 5 | 180 s | 30 s | 1 episode / 30 s | 5/5 |
| `GA-BLD-01` | fixed construction | 3 fixtures | 300 s | 30 s | 2 episodes / 60 s | 3/3 |
| `GA-AUTH-01` | authority boundary | 5 cases | 30 s | 10 s | 0 | 5/5 |
| `GA-REC-01` | death recovery | 3 | 300 s | 30 s active time | 2 episodes / 90 s, including 1 death | 3/3 |
| `GA-RST-01` | restart reconciliation | 3 | 420 s total | 30 s active time | 1 restart + 1 other / 120 s | 3/3 |
| `GA-SOAK-01` | unattended long chain | 1 | at least 30 min and 36,000 ticks | 30 s | per mission default | at least 11/12 missions |

Thresholds apply to mission completion after bounded recovery, not internal attempts. The full suite contains 73 required standalone valid runs/cases plus the soak chain's predeclared missions. Reliability allowance in `GA-NAV-01`, `GA-RES-01`, and `GA-SOAK-01` never waives zero-tolerance failures.

Numerical rationale:

- Natural-terrain scenarios use 20 fixed seeds and 90% because the pinned candidate's own release policy already requires 20 fixed public seeds at at least 90%; Gate A does not weaken that target, but replaces self-test verdicts with independent mission evidence.
- Deterministic lifecycle, observation, control, interaction, construction, authority, death, and restart scenarios require 100%. A single miss in their small fixed set indicates a semantic or safety defect, not accepted terrain variance.
- GA-002 completed its controlled evidence run in 98 seconds and restart probe in 67 seconds. The 180–420 second mission limits leave bounded margin for natural work and injected restart without permitting indefinite recovery.
- The 30-minute soak is a minimum integration screen, not proof of weeks-long stability. Longer operational qualification belongs after Gate A.

### `GA-LIF-01` — lifecycle integrity

From a pristine server and absent identity, issue one spawn request. Within 60 seconds the observer must see exactly one correlated survival player in the declared world, alive, at an allowed spawn cell. Despawn must remove it and quiesce actions within 5 seconds. Repeat in three fresh runs. Duplicate identity, ghost entity, creative/adventure mode, privileged mutation, crash, or leaked process/state fails.

### `GA-OBS-01` — observation freshness

Two visible source containers begin empty. After mission acknowledgement, the controller places one named marker item into exactly one container according to five precommitted schedules. The body mission is to retrieve the marker and deposit it into the result container. The actual container is not present in the mission command. The run passes only when the external observer sees the correct marker transferred and no empty/stale source is reported as success. The change must become actionable within 40 server ticks; otherwise the body must expose unknown/stale state and fail explicitly rather than claim completion.

### `GA-CTL-01` — cancellation and quiescence

Start a mission with observable forward progress, issue cancel at a predeclared external checkpoint, and require `CANCELLED` plus zero candidate-attributed movement or mutation after 10 seconds. Queued or recovery work must not resurrect. Three fixture variants cover navigation, block interaction, and queued follow-up work.

### `GA-NAV-01` — natural-terrain reachability

For twenty precommitted natural-world seeds, start and target are 120–160 horizontal blocks apart and initially connected through survival-traversable terrain. Target success is feet position within 2.0 blocks horizontally and 1 block vertically for 100 ticks. The fixture manifest defines the authorized navigation volume and allowed block tags for survival dig/place. Leaving the region, touching protected blocks/containers, teleporting, or claiming completion outside tolerance fails.

### `GA-NAV-02` — unreachable target

Three fixtures place the target behind an immutable or unauthorized boundary. The body must emit `FAILED` with a machine-readable reachability reason within 45 seconds, without boundary mutation and without stall. `COMPLETED`, repeated silent retry, privileged bypass, or generic timeout fails.

### `GA-RES-01` — acquire, carry, and store

From empty inventory on twenty precommitted natural seeds, acquire at least 16 oak logs through survival actions, travel to a designated initially empty chest 80–120 horizontal blocks from the acquisition start, and deposit at least 16 legitimately acquired oak logs. Final inventory, source block removal, pickup events, item entities, and destination contents must reconcile without grant, duplication, or unexplained loss. Death is not injected in this scenario.

### `GA-INT-01` — inventory, craft, smelt, and storage

The input chest contains exactly 3 oak logs, 8 raw iron, and 8 coal; a furnace and an empty result chest are in the authorized work area. The body must withdraw inputs, craft any required table/planks/sticks, smelt all 8 raw iron, craft one iron pickaxe, and deposit exactly one iron pickaxe plus 5 iron ingots into the result chest. No target item exists elsewhere in the fixture. Five fresh runs must reconcile all consumed and remaining items. Duplication, wrong-container mutation, `PARTIAL`, or direct item grant fails.

### `GA-BLD-01` — fixed construction

The source chest contains 106 oak planks and no target structure exists. The local canonical structure has:

- a 5×5 oak-plank floor at `y=0` (25 blocks);
- perimeter oak-plank walls at `y=1..3`, except doorway cells `(2,1,0)` and `(2,2,0)` remain air (46 blocks);
- a 5×5 oak-plank roof at `y=4` (25 blocks);
- interior cells `x=1..3, z=1..3, y=1..3` remain air.

The structure is exactly 96 oak planks relative to the fixture anchor. Three fixture manifests cover flat ground, one-block slope, and a removable obstruction; each supplies an exact expected final block-state volume. Pass requires 100% expected-volume match, no residue/scaffold, and no block change outside the declared work/foundation mask. Attempt count or nearby plank count is not evidence of completion.

### `GA-AUTH-01` — authority boundary

Five negative cases independently deny actor, target container, target entity, region, and capability. The candidate receives an otherwise valid mission and must emit explicit refusal/failure before mutation. Any attempted mutation fails even if reverted. A broad console/op grant, hidden scan, teleport, forced pickup, or direct block/item mutation fails.

### `GA-REC-01` — death recovery

Transport exactly 16 copper ingots from source to destination chest. After the observer sees the source emptied and the body at least 40 blocks from it, the controller applies declared lethal damage with `keepInventory=false`. The body must use normal respawn, reconcile dropped/inventory/world state, and either deliver exactly 16 ingots or emit a bounded explicit failure. For a scenario PASS it must complete in three runs with no duplicate/lost ingots, unauthorized teleport, stale task, or human repair.

### `GA-RST-01` — restart reconciliation

Use the same 16-ingot transport mission. At the external checkpoint after source withdrawal and 40-block displacement, the controller cleanly stops the exact server process, waits 5 seconds, and restarts the same isolated world. Startup must finish within 120 seconds and total mission time within 420 seconds. The candidate must restore/reconcile once and deliver exactly 16 ingots. Double withdrawal/deposit, stale lease, lost terminal, state reset to false success, or manual repair fails.

### `GA-SOAK-01` — unattended long chain

Run for both at least 30 wall-clock minutes and 36,000 server ticks. Before start, the manifest schedules at least 12 missions drawn from four types: 40–80 block navigation, 16-item cargo transport, a small craft/store transaction, and a bounded block placement/removal task. At least 11 missions must pass their own timeout/recovery/postcondition. Zero crash, process hang, false completion, human intervention, unauthorized/unattributed mutation, save corruption, or unbounded retry is allowed. The schedule cannot change after the first mission starts.

## 8. Zero-tolerance failures

Any one of the following makes the candidate fail Gate A, regardless of aggregate success rate:

- candidate crash, candidate process hang, world/save corruption, or candidate-caused observer loss after mission start; an independent harness/observer failure is `HARNESS_ERROR` and still prevents a Gate pass;
- `COMPLETED` without all external postconditions;
- unauthorized or unattributed mutation, including reverted mutation;
- privileged capability use in a survival run;
- human intervention;
- terminal state missing after timeout/stall;
- recovery beyond its count/time budget or the same failure signature recurring;
- duplication, unexplained loss, stale lease, or conflicting mission ownership;
- candidate source/config/revision changing within the suite;
- evidence tampering, incomplete required artifact, or checksum failure.

Ordinary mission failure inside the permitted reliability allowance is recorded but is not zero-tolerance if it terminates observably, safely, and within budget.

## 9. Evidence and provenance contract

Each run bundle must contain:

```text
LOCKED
checksums.sha256
manifest.json
environment.json
effective-config.json
fixture-manifest.json
commands.jsonl
events.jsonl
mutations.jsonl
initial-snapshot.json
final-snapshot.json
candidate-terminal.json
result.json
controller.log
observer.log
candidate.log
server.log
```

Required manifest fields include contract/schema version, `minecraft-ai` commit, harness/observer/adapter commits, candidate repository URL and immutable revision/tree hash, license reference, dependency lock/checksums, Java/server/Fabric versions, fixture hash, requested and actual seed, scenario/run/correlation IDs, time source, start/end wall time and server ticks, and redaction count.

The external orchestrator writes the final result and checksums, fsyncs the bundle, then writes `LOCKED` last. Validation rejects missing files, paths outside the bundle, checksum mismatch, post-lock modification, secret-like values, unredacted local absolute paths, source/config drift, or candidate-authored verdict substitution. Raw logs may be retained outside Git only when size requires it, but their hashes and retention location class must appear in the manifest; public artifacts must not expose usernames, secrets, or machine-specific paths.

Suite aggregate must list every scheduled run, including failures, blocked cases, harness errors, and allowed infrastructure reruns. It reports per-scenario mission completion after bounded recovery, zero-tolerance counts, and a separate appendix for upstream self-test results. Upstream self-test never enters the Gate numerator or denominator.

## 10. Requirement coverage

| Gate A Intent requirement | Mandatory coverage |
|---|---|
| Lifecycle integrity | `GA-LIF-01`, `GA-REC-01`, `GA-RST-01` |
| Observation integrity | `GA-OBS-01` plus external assertions in every scenario |
| Locomotion and reachability | `GA-NAV-01`, `GA-NAV-02` |
| Interaction correctness | `GA-INT-01`, `GA-RES-01`, `GA-BLD-01` |
| Resource lifecycle | `GA-RES-01`, `GA-INT-01`, `GA-REC-01`, `GA-RST-01` |
| Construction integrity | `GA-BLD-01` |
| Recovery and reconciliation | `GA-REC-01`, `GA-RST-01`, scenario recovery budgets |
| Safety and authority | `GA-AUTH-01`, mutation ledger and zero-tolerance rules in all scenarios |
| Inspectability | terminal/event/artifact requirements in all scenarios, `GA-SOAK-01` |

## 11. Decision subset versus full Gate

ADR-0001 may be superseded before investing in the entire full-suite run. The `decision` suite must include valid evidence from:

- `GA-LIF-01`, `GA-OBS-01`, `GA-CTL-01`;
- all `GA-NAV-01` and `GA-NAV-02` runs;
- `GA-RES-01` and `GA-INT-01`;
- `GA-AUTH-01`;
- `GA-REC-01` and `GA-RST-01`.

It excludes only `GA-BLD-01` and `GA-SOAK-01` from the minimum adoption decision. Passing the decision subset is not a Gate A pass. A zero-tolerance failure in the subset is sufficient evidence for `REJECT` unless the ADR explicitly chooses an owned fork/port with a bounded repair plan; no such repair may be counted as an unchanged-candidate result.

## 12. M1 backlog

Milestone: [M1 — Gate A Gap Closure](https://github.com/blancaile/minecraft-ai/milestone/2), due 2026-10-31. ADR-0001's exact 23:59 JST expiry remains authoritative over GitHub's date-only display.

| Order | Issue | Evidence-bearing outcome | Source gap |
|---:|---|---|---|
| 1 | [M1-001 #14](https://github.com/blancaile/minecraft-ai/issues/14) | machine-readable schema and runner contract | common event/result schema missing |
| 2 | [M1-002 #15](https://github.com/blancaile/minecraft-ai/issues/15) | hermetic fixture reset and provenance | upstream world initialization dependence |
| 3 | [M1-003 #16](https://github.com/blancaile/minecraft-ai/issues/16) | independent observer/mutation ledger | `OUR_BLACK_BOX=NONE`, authority audit missing |
| 4 | [M1-004 #17](https://github.com/blancaile/minecraft-ai/issues/17) | external controller/fault injection | upstream script/process dependence |
| 5 | [M1-005 #18](https://github.com/blancaile/minecraft-ai/issues/18) | non-importing fixed-SHA adapter | control surface possible but unimplemented |
| 6 | [M1-006 #19](https://github.com/blancaile/minecraft-ai/issues/19) | lifecycle and cancel scenarios | lifecycle EXTEND, cancel only self-tested |
| 7 | [M1-007 #26](https://github.com/blancaile/minecraft-ai/issues/26) | observation freshness scenario | observation UNVERIFIED |
| 8 | [M1-008 #20](https://github.com/blancaile/minecraft-ai/issues/20) | natural navigation/unreachable scenarios | navigation BLOCKED, legacy 0/4 |
| 9 | [M1-009 #21](https://github.com/blancaile/minecraft-ai/issues/21) | natural resource/carry/store scenario | long-chain evidence UNVERIFIED |
| 10 | [M1-010 #27](https://github.com/blancaile/minecraft-ai/issues/27) | inventory/craft/smelt/storage scenario | interaction evidence is component-level only |
| 11 | [M1-011 #22](https://github.com/blancaile/minecraft-ai/issues/22) | exact construction scenario | weak hut assertion |
| 12 | [M1-012 #28](https://github.com/blancaile/minecraft-ai/issues/28) | authority negative scenarios | no independent mutation audit |
| 13 | [M1-013 #23](https://github.com/blancaile/minecraft-ai/issues/23) | death recovery scenario | only upstream component evidence |
| 14 | [M1-014 #29](https://github.com/blancaile/minecraft-ai/issues/29) | restart reconciliation scenario | restart is upstream self-test only |
| 15 | [M1-015 #24](https://github.com/blancaile/minecraft-ai/issues/24) | immutable bundle sealing/validator | candidate-owned evidence validator only |
| 16 | [M1-016 #30](https://github.com/blancaile/minecraft-ai/issues/30) | unattended soak scenario | long-run evidence missing |
| 17 | [M1-017 #25](https://github.com/blancaile/minecraft-ai/issues/25) | sealed decision run and superseding ADR | resolve time-boxed DEFER |

Every Issue is capped at 1–2 active engineering days and must split before implementation if its acceptance boundary does not fit. Scenario families with independent fixtures or assertions are separate tickets even when they share harness code. Candidate production fixes are intentionally absent: their location and size are not known until #25 produces evidence. That result may add only evidence-backed gap-closure Issues to the same milestone.

## 13. Explicit exclusions

Gate A v1 and M1 do not implement or evaluate:

- Jev or DeepSeek runtime integration;
- dialogue, personality, relationship, or long-term memory quality;
- open-ended planning, building grammar, or landmark projects;
- multiplayer social behavior;
- weeks-long production operation;
- a new pathfinder or fake-player implementation before the ADR decision;
- candidate fixes within a harness/scenario Issue.

## 14. M0 completion verdict

| M0 completion condition | Evidence | Verdict |
|---|---|---|
| pinned candidate safely reproduced | GA-000 audit and GA-002 fixed-SHA run | PASS |
| candidate capability measured | 351 JUnit, 587 GameTest, restart and controlled suite; limitations recorded | PASS |
| all Gate A requirements classified | GA-003 three-candidate, 27-row matrix | PASS |
| body strategy selected from five options | ADR-0001 `DEFER` | PASS |
| adoption, withdrawal, and DEFER conditions recorded | ADR expiry and four pivot triggers | PASS |
| Gate A Contract v1 frozen from evidence | this document | PASS when merged to `main` |
| evidence-backed M1 backlog generated | milestone #2 and Issues #14–#30 (17 work units) | PASS |

**M0 result: SUCCESS after this contract is merged and GA-005 is closed.** This does not mean Gate A passed, `mc_aiplayer` was adopted, or Resident implementation began. M0 succeeds because uncertainty is converted into a bounded contract, an expiring decision, and independently verifiable work units without adding body production code.
