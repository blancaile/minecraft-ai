# M1-002 hermetic fixture and provenance results

Issue: [M1-002 #15](https://github.com/blancaile/minecraft-ai/issues/15)

実行日: 2026-09-19 (Asia/Tokyo)

## Result

**PASS — candidate-neutralなfixture seal/reset、provenance、exact-process
lifecycle、network/secret/cleanup policyを実装し、WindowsとWSL2で検証した。**

これはMinecraft server、body候補、scenarioを起動した結果ではなく、後続の
M1-003〜005が依存できる隔離・再生成境界の検証結果である。Gate A PASSや
`mc_aiplayer`採用を意味しない。

## Fixed fixture

| Item | Value |
|---|---|
| Fixture ID / version | `server-1.21.3-pristine` / `v1` |
| Minecraft | `1.21.3` |
| Fabric Loader | `0.18.4` |
| Fabric API | `0.114.1+1.21.3` |
| Java contract | major version `21` |
| Payload / canonical snapshot SHA-256 | `fdd104b06df161bac5aa6dcecdc58e743ac949b980590147f7683ca748de4b56` |
| Effective config SHA-256 | `9d9184bf5bc0d28080255d63c3b9eba7c8021be596c5f4d7ad806640e99eb131` |
| Dependency manifest SHA-256 | `3ab2909cc7aeff9b309ae2d578c223a3d01313e20980169e6555203106f7fa65` |

依存lockとrun provenanceにはMojang server、Fabric Loader、intermediary、
Fabric API、GA-002で使用したTemurin JDK packageのbyte数と実測SHA-256を固定し、
lockには各公式HTTPS取得先も記録した。
バイナリ自体はrepositoryへcommitしない。
取得済みのMojang/Fabric top-level artifact 4件はlockとのbyte/hash一致を確認し、
Temurin packageもGA-002保存物とのbyte/hash一致を再確認した。このlockは
top-level input lockであり、実行時に解決される推移的依存の完全なclosureは
M1-004がserver起動前に固定・記録する。

## Reset and provenance probe

同じsealed fixtureから異なるrun IDへ2回prepareした。両方の
`copied_payload_sha256`はfixture hashと同じ
`fdd104b06df161bac5aa6dcecdc58e743ac949b980590147f7683ca748de4b56`となった。
既存run IDの再利用は拒否され、片方へ追加した模擬world stateは他方へ現れない。

Windows probeでは、次をprovenanceへ記録した。

| Item | Observed value |
|---|---|
| Java | Oracle Java `21.0.9` |
| Java executable SHA-256 | `61033fd291e113d915eb1cfbc07100d8514b22ddb38f9b1b1385b727f06b7d52` |
| Network policy | `loopback_only` |
| Secret policy | `forbidden_and_environment_allowlisted` |

WSL2でもGA-002のTemurin `21.0.12.1+1`を使用して2回prepareし、双方の
`server.properties` SHA-256が
`54747ea7cfb13bd78ebe6e2703884168aee0c9fc4219c935072048d8606bd079`
で一致した。Temurin Java executable SHA-256は
`2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d`だった。

全probe後、provenanceを持つ停止済みrunだけを個別cleanupし、run rootも空で
あることを確認した。

## Process and policy tests

- `ManagedProcess`が所有するsubprocessだけをPID単位で停止し、同時に起動した
  unrelated processが生存することを確認した。
- Windowsでは`os.kill(pid, 0)`を使用せず、Win32 process handleの
  non-signaling queryでlivenessを判定する。
- live PIDを記録したrunのcleanupは拒否する。
- symlink、secret-like file/content/environment、非loopback bind、RCON/query、
  payload/config/dependency driftを拒否する。
- prepare途中のfailureはstaging directoryを除去し、完成runとして残さない。

## Verification commands and results

```text
python -m harness.gate_a.fixture verify --fixture harness/gate_a/fixtures/server-1.21.3-v1
  VERIFIED; fixture SHA-256 fdd104b0...de4b56

python -m unittest discover -s harness/gate_a/tests -v
  30 tests; PASS; 1 platform-specific skip on Windows

python -m compileall -q harness
  PASS

WSL2: python3 -m unittest harness.gate_a.tests.test_fixture -v
  16 tests; PASS; 1 Windows-specific skip
```

## Decision / Finding

M1-002の隔離fixture/reset/provenance境界は後続Issueから利用可能である。
serverのreadiness、dynamic port discovery、server command/fault injectionは
M1-004、候補依存の起動方法はM1-005へ残す。runtimeのOS-level outbound egress
sandboxは本Issueでは実装せず、現時点のnetwork保証はMinecraft bind/query/RCON
設定のloopback boundaryである。
