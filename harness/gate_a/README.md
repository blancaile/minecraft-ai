# Gate A schema and runner interface

This directory is the candidate-neutral contract boundary for [Gate A Contract v1.0](../../docs/gates/gate-a-v1.md). It does not import, link, start, or evaluate a Minecraft body candidate.

## Implemented in M1-001

- JSON Schema Draft 2020-12 bundle: `schema/gate-a-v1.schema.json`
- document types: `contract`, `run_manifest`, `event`, `mutation`, `terminal`, `result`, `suite_summary`
- cross-field validation for threshold counts, fixed seeds, PASS semantics, recovery budgets, safety counters, and suite aggregates
- valid and intentionally invalid fixtures
- schema/instance/example validation CLI

## Implemented in M1-002

`fixture.py` provides a candidate-neutral isolation boundary before a server or
body process is connected:

- verifies the sealed Minecraft 1.21.3 / Fabric Loader 0.18.4 / Fabric API
  0.114.1+1.21.3 fixture and its SHA-256 inventory;
- copies the pristine payload to an exclusively created directory for every
  run and records a canonical reset digest;
- records the observed Java 21 executable hash, OS, game/Fabric versions,
  dependency-lock hash, and effective-config hash in `.gate-a/provenance.json`;
- requires loopback-only server binding and disables query, RCON, operator
  broadcasts, proxy connections, and online authentication in the isolated
  test fixture;
- rejects symlinks, special files, secret-like files/content/environment
  variables, payload drift, reused run IDs, and unsafe cleanup targets;
- owns a concrete subprocess handle and stops that exact PID. It never searches
  or kills processes by name.

Verify and prepare the checked-in fixture from the repository root:

```powershell
python -m harness.gate_a.fixture verify `
  --fixture harness/gate_a/fixtures/server-1.21.3-v1
python -m harness.gate_a.fixture prepare `
  --fixture harness/gate_a/fixtures/server-1.21.3-v1 `
  --runs-root harness/gate_a/runs `
  --run-id local-reset-probe
python -m harness.gate_a.fixture cleanup `
  --runs-root harness/gate_a/runs `
  --run-id local-reset-probe
```

`seal` creates a new fixture version and refuses to overwrite one. Dependency
binaries are not committed; their official HTTPS locations, byte sizes, and
SHA-256 values are pinned in `dependencies.lock.json`. This is the top-level
input lock; M1-004 must capture the complete runtime-resolved dependency set
before executing evidence runs. M1-004 also owns actual server orchestration,
port discovery, readiness, and fault injection. M1-005 owns candidate launch
integration. This fixture layer does not claim that a Minecraft scenario or
Gate A has passed.

The schema carries both `schema_version=gate-a-schema-v1.0` and `contract_version=gate-a-v1.0`. A breaking field or semantic change requires a new schema version. A changed Gate threshold/scenario requires a new contract version. Producers must not write unknown fields; every evidence object uses `additionalProperties: false` except explicitly open observation payloads such as event details and before/after values.

Candidate-specific class names, internal task phases, log messages, or evidence verdicts are forbidden as required fields. `candidate` provenance and raw adapter output may be recorded, but only `OUR_BLACK_BOX` is accepted as result evidence independence.

## Install and validate

Run from the repository root with Python 3.10 or later:

```powershell
python -m pip install -r harness/gate_a/requirements.txt
python -m harness.gate_a.schema_validate schema
python -m harness.gate_a.schema_validate examples
python -m harness.gate_a.schema_validate instance harness/gate_a/schema/examples/valid/result.json
python -m unittest discover -s harness/gate_a/tests -v
```

`requirements.txt` pins the versions used to implement and test M1-001. Hermetic dependency download, hashes, and environment provenance belong to M1-002; this Issue does not claim that boundary is complete.

Validator exit codes:

| Code | Meaning |
|---:|---|
| `0` | schema/document/examples are valid |
| `4` | validator/tool/I/O failure |
| `5` | schema-shaped contract/config/evidence document is invalid |

## Reserved canonical runner interface

M1-001 freezes this interface but does not implement server execution:

```text
gate-a validate-contract --contract gate-a-v1
gate-a run --candidate <manifest> --suite decision|full --output <new-directory>
gate-a verify --bundle <locked-directory> [--require-pass]
```

Runner exit codes are reserved by the Gate contract:

| Code | Meaning |
|---:|---|
| `0` | operation valid; full-suite `run` uses 0 only for a Gate PASS |
| `2` | candidate/scenario `FAIL` |
| `3` | `BLOCKED` |
| `4` | `HARNESS_ERROR` or invalid artifact |
| `5` | contract/config/provenance error before execution |

M1-004 owns the external controller implementation. M1-015 owns immutable bundle sealing and verification. No command in this directory may synthesize a candidate PASS.

## Semantic invariants beyond JSON Schema

`schema_validate.py` rejects these cross-field contradictions:

- duplicate scenario or aggregate IDs;
- duplicate candidate/harness component names;
- `threshold.total_runs != valid_runs` or minimum passes above total;
- requested/actual mismatch for a fixed seed;
- a `PASS` without `COMPLETED`, with a failed postcondition/violation/safety counter, or beyond recovery budget;
- aggregate outcome counts that do not equal the individually listed runs;
- a Gate `PASS` for a decision subset, incomplete/extra v1 scenario set, failed threshold, blocked run, harness error, or zero-tolerance failure.

These checks validate records. They do not observe Minecraft, prove a postcondition, attribute a mutation, or decide whether an event is truthful; those responsibilities remain with the independent observer and verifier Issues.
