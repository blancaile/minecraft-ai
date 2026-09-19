# Pinned `mc_aiplayer` baseline reproduction

Issue: [GA-002](https://github.com/blancaile/minecraft-ai/issues/5)

実行日: 2026-09-19 (Asia/Tokyo)

対象commit: [`a029fa6a3760fd0f83834c104051b041d986da60`](https://github.com/zoyluoblue/mc_aiplayer/commit/a029fa6a3760fd0f83834c104051b041d986da60)

実行契約: [`mc_aiplayer` provenance and execution-safety audit](mc-aiplayer-supply-chain-audit.md)

## 1. Result

**PINNED UPSTREAM BASELINE REPRODUCED.**

固定SHAを変更せず、secret-freeなWSL2 Ubuntu環境で次を再現した。

- official Gradle wrapper/distribution checksum verification
- Gradle build、JUnit、Fabric GameTest
- production artifact/static invariant check
- evidence validator adversarial self-test
- two-JVM persistence/restart probe
- deterministic strict-survival evidence run
- immutable evidence bundleの`--require-verified` validation

これは`mc_aiplayer`がGate Aを満たす証拠ではない。既存のbuild・self-test・限定scenario・evidence infrastructureが再現できたことだけを示す。

## 2. Execution environment

| Item | Value |
|---|---|
| Host boundary | WSL2 Ubuntu、専用Linux home directory |
| Kernel | `5.15.167.4-microsoft-standard-WSL2 x86_64` |
| Bash | `5.2.21` |
| Git | `2.43.0` |
| Python | `3.12.3` |
| Java | Eclipse Temurin `21.0.12.1+1`、JDK |
| Gradle | `9.4.0` |
| Source | detached fixed SHA、start/end clean |
| Secret environment | credential-like namesを事前検査。API key/tokenをunset |
| Gradle cache/temp | run専用directory |
| LLM | disabled。`DEEPSEEK_API_KEY`なし、`--with-llm`なし |

Windows側`minecraft-ai` workspaceは実行対象にせず、WSLの専用directoryだけを使用した。

## 3. Downloaded execution dependencies

### Gradle

| Artifact | SHA-256 | Result |
|---|---|---|
| `gradle-wrapper.jar` | `55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c` | official Gradle 9.4.0 checksumと一致 |
| `gradle-9.4.0-bin.zip` | `60ea723356d81263e8002fec0fcf9e2b0eee0c0850c7a3d7ab0a63f2ccc601f3` | official checksumと一致 |

検証済みdistributionをrun専用wrapper cacheへ投入してからwrapperを起動した。

### JDK

WSLに最初からあったJava 21はruntimeだけで`javac`を含まなかった。system packageは変更せず、Adoptium APIが返した固定releaseをrun専用directoryへ取得した。

| Item | Value |
|---|---|
| Release | `jdk-21.0.12.1+1` |
| Package | `OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz` |
| SHA-256 | `ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94` |
| Runtime | Eclipse Adoptium Temurin 21.0.12.1+1 LTS |
| Compiler | `javac 21.0.12.1` |

package hashをAdoptium APIのchecksumと照合してから展開した。

## 4. Command results

| Step | Exit | Duration | Result |
|---|---:|---:|---|
| wrapper `--version` | 0 | 約1秒 | Gradle 9.4.0、Java 21を確認 |
| selected shell `bash -n` | 0 | 1秒未満 | PASS |
| first `clean test runGameTest build` | 1 | 87秒 | `ENVIRONMENT_PRECONDITION_FAIL`: WSL既定Javaにcompilerなし |
| verified JDKで`clean test runGameTest build` | 0 | 4分4秒 | PASS |
| `CI_STATIC_CHECK_ARTIFACTS=1 scripts/ci_static_check.sh` | 0 | 1秒 | PASS |
| `scripts/evidence_validate.sh --self-test` | 0 | 8秒 | PASS |
| `scripts/persistence_restart_test.sh` | 0 | 67秒 | PASS |
| deterministic `scripts/evidence_run.sh` | 0 | 98秒 | PASS / VERIFIED |
| `evidence_validate.sh --require-verified` | 0 | 1秒未満 | VERIFIED |

初回build failureはsource defectではなく、Gradle toolchainが`JAVA_COMPILER` capabilityを見つけられなかった環境precondition failureである。ログを成功runと分離して保持し、修正済みsourceとして扱っていない。

## 5. Build and test results

### JUnit

- XML suite files: 65
- testcases: 351
- failures: 0
- errors: 0
- skipped: 0

上流[`TESTING_AND_EVIDENCE.md`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/docs/TESTING_AND_EVIDENCE.md)の「19 classes / 68 tests」という記載とは一致しない。固定commitの実測では351 testcaseだった。原因は本Issueで修正せず、documentation driftまたは集計定義差としてGA-003へ渡す。

### Fabric GameTest

- testcase elements: 587
- required tests passed: 587
- failures reported by server: 0
- server result: `All 587 required tests passed :)`

これはfixed commit messageの主張と一致した。

### Build

- `BUILD SUCCESSFUL in 4m 4s`
- 19 actionable Gradle tasks、19 executed
- production artifact/static invariant: PASS
- warning: deprecated Gradle featuresがあり、Gradle 10互換ではない

## 6. Persistence/restart result

redacted resultは[`evidence/ga-002/persistence-result.redacted.tsv`](evidence/ga-002/persistence-result.redacted.tsv)へ保存した。

| Check | Result |
|---|---|
| overall | PASS |
| profile | `strict_survival` |
| checkpoint | non-default stateをexact restore |
| stale lease | reopened |
| resume | postcondition付きでcompleted |

phase1/phase2のraw server logはGitへcommitしていない。合計約32KBで、WSL専用実行directoryに保持した。

## 7. Deterministic evidence result

redacted/generated metadata:

- [runtime manifest](evidence/ga-002/runtime-manifest.redacted.tsv)
- [runtime result](evidence/ga-002/runtime-result.redacted.tsv)
- [runtime config](evidence/ga-002/runtime-effective-config.redacted.json)
- [original bundle checksums](evidence/ga-002/original-bundle-checksums.sha256)
- [LOCKED metadata](evidence/ga-002/runtime-locked.tsv)

主要結果:

| Item | Value |
|---|---|
| evidence state | `VERIFIED` |
| verification reason | `complete` |
| source snapshot | `git_archive` |
| start/end commit | fixed SHAで同一 |
| start/end worktree | clean |
| requested / actual seed | `20260610` / `20260610`、verified |
| mode | deterministic |
| profile | strict_survival |
| LLM | disabled |
| privileged capabilities | 全4項false |
| secret redactions | 0 |
| scenario result | PASS、9/9 |

9件の内訳:

- capability profile
- cancel without resurrection
- cancel current with queue
- replace queued goal
- replace action only
- replacement start failure
- pause/resume safety stack
- controlled diamond stack
- controlled obsidian half-stack

このsuiteはruntime controlとcontrolled mining contractを検証する。natural long navigation、resource acquisition chain、death recovery、large construction、soakを証明しない。

## 8. Artifact integrity

immutable evidence bundleは68KB、run result log群は約4.4MB、persistence artifactは48KBだった。raw server/build logは公開Git repositoryへ追加していない。

`original-bundle-checksums.sha256`は実行時のraw bundleに対するchecksum記録である。repositoryへ保存したmanifest/result/configはlocal pathや時刻付きlog prefixをredact・整形しているため、このchecksumで直接検証する対象ではない。

主要hash:

| Artifact | SHA-256 |
|---|---|
| runtime `LOCKED` | `442ce8613c87ad224a21c0d6337870e0f67147efa7d9ff9e9fb9f06e407ec3bd` |
| runtime `checksums.sha256` | `c8f15823a21ad96bd1e6aade935fbe279f688df2e0c312e0f7a526951ed3ec5f` |
| successful build/GameTest log | `5e86402eb20f0cf4edb7faf8c3c39fba53d2baf702669ad37f6deba990841436` |
| initial JRE-only failure log | `779f3b34cb2dfeb84ac05aee53863bcfa5c2ca7e355441f28f434e2bf475b270` |
| evidence run summary log | `e4b472051ba061961b82f425eb42cce337511ca39ca046fbed81f67f5e35063f` |
| require-verified log | `727be86d283823309e359269a9bdc40814782f3b3f724d796a9254f8099ab338` |
| persistence summary log | `d26428038bf6677a52beef3a9c5506c695b451e779e3a0` |

保存したredacted metadataからraw logを再構築することはできない。必要なら同じfixed SHAとcommandで再実行する。hashは今回のlocal raw artifactとの対応を検査するために残す。

## 9. Deviations and non-runs

- 上流GitHub workflow自体は実行していない。監査済みcommandを個別に実行した。
- `quickcheck.sh`、`prod_test.sh`、LLM、story、nightly、mining shard/release gate、pin baselineは実行していない。
- source、test fixture、assertion、config defaultを変更していない。
- 独立Acceptance Harnessは作成していない。
- upstreamへのIssue/PRは作成していない。

## 10. Finding

fixed commitのbuild/test/evidence infrastructureは、条件付き隔離環境で再現できた。特に587 GameTest、two-JVM persistence、immutable VERIFIED bundleは、候補査定を進める基盤として利用価値がある。

一方、再現した強いtest infrastructureをbody reliabilityと同一視してはならない。今回のruntime suiteは9件のcontrolled scenarioで、Gate A Intentが要求する長いmission chainや自然地形の信頼性をほとんど測っていない。また上流文書と実測JUnit件数にdriftがある。

GA-003では、各Gate A requirementについて`UPSTREAM_SELF_TEST`と`OUR_BLACK_BOX`を分け、既存の587 GameTestや9/9 evidenceが具体的にどこまでを覆うかをsource/test単位で評価する。
