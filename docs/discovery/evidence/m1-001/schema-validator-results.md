# M1-001 Gate A schema validator results

- Date: 2026-09-19 (Asia/Tokyo)
- Issue: [M1-001 #14](https://github.com/blancaile/minecraft-ai/issues/14)
- Scope: schema, validator, examples, and reserved runner interface only

## Result

**PASS — the M1-001 acceptance boundary is implemented and locally reproducible.**

The versioned Draft 2020-12 schema represents contract scenarios, run provenance, events, mutations, candidate terminals, independent run results, and suite summaries. Cross-field validation rejects false PASS records, safety counters, timeout/stall/recovery overruns, seed drift, threshold/count contradictions, and Gate PASS for a decision-only suite.

No Minecraft server, candidate adapter, observer, process controller, bundle sealer, body fix, or Resident production code was implemented.

## Environment

| Item | Value |
|---|---|
| Python | 3.13.3 |
| jsonschema | 4.26.0 |
| Host | Windows workspace; validator is platform-independent Python |

Pinned Python requirements are recorded in `harness/gate_a/requirements.txt`. Hermetic download and package hashes are explicitly deferred to M1-002.

## Commands and outcomes

| Command | Outcome |
|---|---|
| `python -m harness.gate_a.schema_validate schema` | PASS — schema is valid Draft 2020-12 |
| `python -m harness.gate_a.schema_validate examples` | PASS — 7 valid documents accepted, 4 intentionally invalid documents rejected |
| `python -m unittest discover -s harness/gate_a/tests -v` | PASS — 14/14 tests |
| `python -m compileall -q harness` | PASS |
| `python -m pip install --dry-run --disable-pip-version-check -r harness/gate_a/requirements.txt` | PASS — all five exact requirements resolve in the test environment |

`ruff` was not installed in the environment, so no Ruff result is claimed. It is not an M1-001 acceptance requirement.

## Artifact integrity

| Artifact | SHA-256 |
|---|---|
| `harness/gate_a/schema/gate-a-v1.schema.json` | `871fc6e470cfc0d57941dd892cac39d8af7cd46b5768a0baa09240ee504edf56` |

The final merge commit is recorded in Issue #14 after merge. This checksum covers the schema before that commit and is checked again during PR verification.

## Finding

M1-001 establishes the record contract but does not establish truth. JSON documents can now be rejected for structural and semantic contradiction; only M1-003's independent observer and later postcondition verifier can prove that recorded Minecraft state is accurate.
