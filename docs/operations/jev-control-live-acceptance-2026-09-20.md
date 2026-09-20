# Issue #38: Paper / real Jev acceptance (2026-09-20)

## Result and limits

P0 acceptance is complete: **4 real-Jev runs / 129 completed decision cycles**, three simple goal arrivals, and executed/reported obstacle adaptation probe. **Obstacle adaptation failed within its declared budget**; P0 explicitly permits this finding after execution and honest reporting. This is not P1 completion, general navigation capability, Gate A acceptance, or a multi-bot result.

Final artifact: `jev-control-paper-0.2.0.jar`, SHA-256 `165fd5ba4ac7ec9235e8019d3e283d56b97a6d8b4b1b32d57100b95b41c69344`.
Paper **1.21.11 build 116**, Java 21, model **jev-1.13.0**, fixed production endpoint `https://api.typesafe.ai/v1/systemone`. No alternate model, default action, retries, pathfinder, movement teleport or velocity assignment.

## Predeclared fixture and budgets

Isolated loopback Paper, stone floor x/z -63..63 at y=80; body starts `(0.5,81,0.5)`. Initial yaw is fixture-set **before** the run; no teleport commands occur after `jev start`. Platform construction is isolated, not on the shared server. Each episode: 60 decisions, 120 seconds, 10-second HTTP timeout, maximum snapshot age 200 ticks, four-tick inputs, observation radius 3, arrival radius 1, distance bound 64. At most eight episodes; stop after at least four preset episodes and 100 completed cycles. `plan.json` is saved before API calls.

| Setting | Initial yaw | Goal | Completed cycles | Result |
|---|---:|---|---:|---|
| south | 0 | `(0.5,81,20.5)` | 23 | GOAL_REACHED |
| east-facing-south | 0 | `(20.5,81,0.5)` | 23 | GOAL_REACHED |
| west-facing-north | 180 | `(-19.5,81,0.5)` | 23 | GOAL_REACHED |
| obstacle | 0 | `(0.5,81,20.5)` | 60 | BUDGET_EXCEEDED; adaptation FAILED |

Run IDs respectively: `360cf6c1-e375-424f-acbe-665a310f141f`, `590468ef-530e-4310-ae80-7358dbd27a61`, `88c2bce7-6a9d-49a2-802c-de7ae0fe2836`, `8afb134e-e012-49df-8004-002e875f9ccb`.

- API latency p50 **281 ms**, p95 **369 ms**; maximum accepted snapshot age **18 ticks**.
- Maximum measured server tick interval during runs **63.639 ms** (not a TPS guarantee).
- All 129 inputs lasted exactly four server ticks. Observation → decision → input → result IDs, previous result linkage, real displacement, rotation and goal radius were checked from JSONL.
- All eight candidates remained available in these grounded runs; no goal-based candidate filtering. Health remained 20. After settling, horizontal velocity was below 0.001 in every episode.
- South selected FORWARD 23 times; east and west selected STRAFE_LEFT 23 times each, producing actual displacement in the corresponding world directions. Model probabilities, candidate sets and exclusions are retained per observation/decision.

## Dynamic obstacle probe (failed adaptation, not hidden)

After three completed cycles, fixture placed stone at x=-1..1, y=81..83, z=4. Recorded intervention tick: 1207. Before observation `2e9b060d-af1c-49ea-9aca-8c9e12d8642e`; first subsequent wall-observing snapshot bound to a decision/input: `e44618f2-e046-4731-ac20-771c36a68eaa`. Both retain the same eight legal candidates. The verifier requires newly observed stone above floor level at the specified coordinates and a subsequent Jev choice/input bound to that observation.

Choices before: FORWARD. After observing the wall, Jev also selected WAIT, STRAFE_LEFT, BACK, TURN_RIGHT and TURN_LEFT. Total actions: FORWARD 34, STRAFE_LEFT 21, BACK 2, WAIT 1, TURN_RIGHT 1, TURN_LEFT 1. The body ended near `(18.289,81,20.843)`, away from its goal, with health 20. **Choice changed, but the target was not reached.** No operator supplied an escape action, removed the obstacle, or adjusted the goal/budget mid-run. P1 should investigate progress maintenance after local obstacle avoidance; no P1 implementation is claimed here.

## Failure injection (separate from real API cycles)

Six isolated Paper episodes, dedicated dummy credential and explicit JVM loopback endpoint. Production credentials are rejected by the fixture endpoint guard. Each episode first completes one FORWARD input, then receives its injected second-response fault:

| Fault | Terminal | Goal-requiring verifier subprocess exit |
|---|---|---:|
| HTTP 503 | ERROR | 1 |
| connection closed without response | ERROR | 1 |
| unknown action | ERROR | 1 |
| 2-second delayed response, age limit 5 ticks | ERROR / Stale observation | 1 |
| 2-second response delay, timeout 1 second | ERROR | 1 |
| stop while response pending; attempt delayed delivery | CANCELLED | 1 |

Exactly two requests per case; no retry/fallback and no second input. After delayed-response attempt and settling, inputs remain released, horizontal velocity <0.001, health >0. The aggregate fault test exits 0 only because the six expected failures, nonzero child-verifier exits and physical release checks pass. These six dummy decisions are **not** counted toward real-Jev acceptance.

## Findings and corrections retained

1. README already documents `.env` / `jev_api_key` and the existing loader. Reused `load_jev_api_key`, without printing the file/key or using the probe's unpinned model. Local live runner passes the key only in the child Java environment; config contains `env:JEV_API_KEY`.
2. First shared real run reached its goal in three decisions, but SFTP `WriteAllText` left trailing bytes when restoring a shorter configuration. Overall run remains FAILED. Changed writing to a truncating stream, recovered the original JSON prefix (blank key, original budgets), checked config validity and bot absence, then repeated successfully. No failed evidence was replaced.
3. Initial isolated batch: south reached in 23 cycles; east exhausted 60 cycles moving away; north-facing west attempt completed 46 cycles then left the small floor and hit the distance bound while falling. Batch remains FAILED, with all **129** completed cycles and raw traces retained separately; they are not needed for final acceptance totals.
4. Added mechanical yaw-based input vectors and goal projections (`ControlFrame`). It never ranks/selects/removes actions. Enlarged fixture floor so a wrong direction does not immediately leave the test platform. Final three direction presets all reached their goals. This small before/after observation is not a statistical generalization claim.
5. No temporary server-console diagnostic statements were added. Structured run evidence remains in dedicated JSONL; shared `latest.log` and other plugins' logs were not deleted.

## Shared-server final deployment and live check

- Deployed final SHA above and performed one hash-confirmed reload. Build identifier verified in fresh `JEV_READY` and `jev status`.
- Shared body experiment `e0bab56d-b6b9-4512-9980-2539727feb02`: PASSED (spawn, real movement/release, turn, observe, despawn, log/trace verification).
- Final real API experiment `live-2a6c6871-a64a-4f29-8b19-a1a3129ef4e0`: **3 cycles / GOAL_REACHED**, near the online `Philia_Gray`; generated `(-15.5,-60,2.5)`, goal `(-15.5,-60,5.5)`. Trace `17948906-5f0c-4150-b5c3-037c2266263d.jsonl`; independent audit PASSED. API p50 452 ms / p95 688 ms; max age 14 ticks; max tick interval 51.537392 ms.
- Temporary key/config restored; bot stopped/despawned. Independent final status has the same artifact SHA and `bot=none`. Shared terrain/player settings were not changed.
- Reload window contains 12 ERROR lines from other plugins/data packs, 0 JevControl ERROR lines. Jev activation succeeds; this is **not** a claim of whole-server health.

## Reproduction and checks

Run from the task worktree; set existing SFTP credentials as documented, never in commands/source. Live calls require explicit authorization.

```powershell
tools/runtime/build.ps1 -Smoke
python tools/runtime/paper_acceptance.py --mode faults --execute
python tools/runtime/paper_acceptance.py --mode live --key-file <existing-.env-path> --execute
tools/runtime/experiment.ps1 -Scenario tools/runtime/near-player.example.json -Deploy -Reload -Execute
tools/runtime/live-near-player.ps1 -KeyFile <existing-.env-path> -Player Philia_Gray -Execute
python tools/runtime/paper_acceptance.py --audit-directory <paper-live-evidence-directory>
```

Build: **13 Java tests**, **7 offline deployment checks**, **3 evidence-verifier tests**, **22 actual-Paper body checks**, plus **6 runtime fault cases** pass. Runtime-experiment skill validates. CI now runs offline evidence tests and isolated faults, **never real API calls**; only explicit nonsecret artifacts are uploaded.

Local evidence under `.runtime-harness/` (raw logs intentionally not committed):

- Final live: `paper-live-08cd855d4b68/{plan.json,verification.json,audit-14c05428.json,plugins/JevControl/traces/}`. `verification.json` SHA-256 `8a6d8a91c4bfb59589e7c58226222d9c0a5070ba33a5bcb49cf114e84bca4c44`.
- Final faults: `paper-faults-3ba924bf68cf/{verification.json,audit-fe30138b.json,plugins/JevControl/traces/}`. Report SHA-256 `3d8ba85f86fa656e7046d448d803d0cd8a3b022cc251d66cf3c656669ae0147b`.
- Final body smoke: `paper-smoke-aad5deb359dc/verification.json`.
- Initial failed live batch: `paper-live-7fe943b87072/audit-1215f1f5.json` and raw traces (includes the third run whose cleanup verification failed).
- Initial shared restoration failure: `remote-live-aaf775f2-fa02-406b-8f07-6e5a3c9d5f56/`; recovery: `remote-live-config-recovery/`; successful repeat: `remote-live-0bd785e7-1cde-4d10-8b10-2dddb9066bfd/audit-61de37a3.json`.
- Final shared activation/body: `remote-e0bab56d-b6b9-4512-9980-2539727feb02/`; final real loop: `remote-live-2a6c6871-a64a-4f29-8b19-a1a3129ef4e0/audit-c4ae2fc2.json`; final no-bot status: `remote-issue38-final-status/`.

Failure records, setup/manual runs and mock decisions are distinguished from the final 129 real cycles. No evidence was removed to make the result pass. Known remaining limitation is obstacle-goal adaptation; later tasks retain the observations rather than adding a Java navigation fallback.
