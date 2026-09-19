# `mc_aiplayer` provenance and execution-safety audit

Issue: [GA-000](https://github.com/blancaile/minecraft-ai/issues/4)

監査日: 2026-09-19 (Asia/Tokyo)

監査対象:

- repository: [`zoyluoblue/mc_aiplayer`](https://github.com/zoyluoblue/mc_aiplayer)
- commit: [`a029fa6a3760fd0f83834c104051b041d986da60`](https://github.com/zoyluoblue/mc_aiplayer/commit/a029fa6a3760fd0f83834c104051b041d986da60)
- parent: `5844a032c8436e27e41d440c0c0d36ef145e18fb`

## 1. Decision

**CONDITIONALLY APPROVED FOR GA-002.**

固定SHAの選択済みcommandだけを、秘密情報を持たないdisposable Linux環境で実行してよい。repository全体、任意script、GitHub workflowを包括的に信用したという意味ではない。

次は明示的に禁止する。

- paid LLM、`DEEPSEEK_API_KEY`、`--with-llm`を使う経路
- host上の既存Gradle/Minecraft processをglobalにkillするscript
- 既存world、mods、baseline、reportを変更するscript
- checksumなしでbinaryを追加downloadする補助script
- upstream workflowのそのままの再実行
- fixed SHAへのpatch、fixture変更、assertion緩和

GA-002は本書の実行契約に従い、逸脱が必要ならGA-000を再openする。

## 2. Audit method and limitation

GitHub APIから固定SHAのcommit metadata、tree、build設定、wrapper、source、scripts、workflowsを取得し、静的に監査した。上流のGradle、Java、shell script、Minecraft serverはGA-000では実行していない。

静的監査は、Gradle pluginやdownload後dependencyの内部動作まで安全と証明しない。GA-002では、これらを第三者コードとして隔離した環境で実行する。

## 3. Provenance

| Item | Finding |
|---|---|
| Repository | public、non-fork、not archived、not disabled |
| Default branch | `main` |
| Fixed commit | SHAを完全指定。監査時のdefault branch HEADと同一 |
| Commit author/committer | `ZoyLuo`、2026-09-02T04:15:18Z |
| Signature | **unsigned / GitHub verification false** |
| Tree API | 489 entries、401 blobs、response not truncated |
| Submodules | 0 |
| Symlinks | 0 |
| Security/provenance policy files | `SECURITY.md`、`CODEOWNERS`、`NOTICE`等は見つからない |

commitが未署名のため、作者の暗号学的identityは確認できない。GA-002はGitHub HTTPSから取得した完全SHAとtree内容を監査対象のidentityとして扱う。

## 4. License and attribution

固定SHAの[`LICENSE`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/LICENSE)はMIT Licenseで、copyrightは`Copyright (c) 2026 zoyluo`。

利用、変更、再配布、sublicenseは許可されるが、substantial portionsを取り込む場合はcopyright noticeとMIT permission noticeを保持する必要がある。EXTEND、PERMANENT_FORK、SELECTIVE_PORTのいずれでも、取り込んだ範囲と原commitを追跡できる形で保存する。

これはlicense本文に基づくengineering上の確認であり、法的助言ではない。

## 5. Repository binary inventory

実行可能なbinary blobとして重要なのは`gradle/wrapper/gradle-wrapper.jar`である。

| Item | Value |
|---|---|
| Size | 48,966 bytes |
| Git blob SHA-1 | `d997cfc60f4cff0e7451d19d49a82fa986695d07` |
| Computed SHA-256 | `55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c` |
| Official Gradle 9.4.0 wrapper SHA-256 | `55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c` |
| Result | **MATCH** |

比較にはGradle公式の[Wrapper verification guidance](https://docs.gradle.org/current/userguide/gradle_wrapper.html#sec:verification)と公式checksum endpointを使用した。

他のbinary-like blobは`promo/`配下の画像であり、最大約5MB。server JAR、Fabric installer、native library、実行binaryはGit treeに含まれていない。`run-prod/`用serverは`.gitignore`対象で、repositoryには同梱されていない。

## 6. Gradle and dependency integrity

固定された主要version:

| Component | Version/source |
|---|---|
| Gradle | `9.4.0`、`services.gradle.org` |
| Java | 21 |
| Fabric Loom | `1.16.2`、Fabric Maven / Plugin Portal |
| Minecraft | `1.21.3` |
| Yarn mappings | `1.21.3+build.2` |
| Fabric Loader | `0.18.4` |
| Fabric API | `0.114.1+1.21.3` |
| JUnit BOM | `6.1.0`、Maven Central |

repositoryは次を持たない。

- Gradle dependency locking
- `verification-metadata.xml`
- dependency artifact checksum allowlist
- version catalog
- `distributionSha256Sum` in `gradle-wrapper.properties`

公式`gradle-9.4.0-bin.zip`のSHA-256は`60ea723356d81263e8002fec0fcf9e2b0eee0c0850c7a3d7ab0a63f2ccc601f3`だが、上流propertiesには固定されていない。

したがってwrapper JAR自体は公式一致だが、Gradle distributionとMaven/Fabric artifactはrepository内checksumで完全固定されていない。GA-002ではisolated cacheを使い、Gradle distribution checksumを実行前に公式値と照合する。dependency download後の完全なartifact provenanceは未解決riskとして残す。

## 7. Build-script effects

[`build.gradle`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/build.gradle)は次を行う。

- GameTestとtest-only harness source setを設定
- project-relative childに限定したharness run directoryを作成
- harness用`eula.txt`と`server.properties`を生成
- GameTest前に`build/run/gameTest`を削除して再作成
- production JARへLICENSEを同梱
- `online-mode=false`のlocal test serverを構成

削除対象`build/run/gameTest`はrepository childに固定されるが、Groovy build scriptとGradle pluginsは任意codeを実行できる。GA-002では必ずdisposable checkout内で実行する。

## 8. Network and credential paths

production sourceの明示的external APIはDeepSeekである。

- config default endpoint: `https://api.deepseek.com`
- runtime request: `/v1/chat/completions`
- credential sources: configの`deepseek.apiKey`、環境変数`DEEPSEEK_API_KEY`
- HTTP header: `Authorization: Bearer ...`

GA-002ではLLM能力を評価しない。`DEEPSEEK_API_KEY`を環境から除去し、isolation configのkeyを空にし、`--with-llm`を禁止する。

Gradle実行には少なくともGradle、Fabric、Maven Central、Minecraft dependency配布元へのnetwork accessが必要になる。実行環境へGitHub token、cloud credential、SSH key、Minecraft/Microsoft account token、Jev/DeepSeek keyを渡さない。

## 9. GitHub workflow audit

workflowは`permissions: contents: read`を宣言しており、通常のCI/nightlyはDeepSeek secretを受け取らない。paid LLMはmanual workflowに分離され、明示確認を要求する。

一方、third-party actionsは完全commit SHAではなくmajor tagで参照されている。

- `actions/checkout@v6`
- `actions/setup-java@v5`
- `gradle/actions/setup-gradle@v6`
- `actions/upload-artifact@v4`
- `actions/download-artifact@v4`

`setup-gradle@v6`は公式仕様上wrapper validationを標準で行うが、mutable tagのaction自体を新しいtrust rootとして追加する。GA-002では上流workflowをimport・triggerせず、監査したcommandを自分たちのdisposable environmentで個別に実行する。

## 10. Script classification

### 10.1 Conditionally allowed for GA-002

次だけを、Section 11の隔離条件下で許可する。

| Command | Purpose | Conditions |
|---|---|---|
| `bash -n <selected scripts>` | shell syntaxのみ | commandを実行しない |
| `./gradlew --no-daemon --console=plain --stacktrace clean test runGameTest build` | unit/GameTest/build | wrapper/distribution確認後、disposable checkout、secret-free |
| `CI_STATIC_CHECK_ARTIFACTS=1 bash scripts/ci_static_check.sh` | source/workflow/artifact invariant | build後、disposable checkout |
| `bash scripts/evidence_validate.sh --self-test` | validator adversarial self-test | isolated `TMPDIR`、secret-free |
| `bash scripts/persistence_restart_test.sh` | two-JVM restart | isolated run directory、secret-free |
| `bash scripts/evidence_run.sh --scenario capability_profile+runtime_control_suite+mining_contract_suite --seed 20260610 --timeout 240 --startup-timeout 480 --profile strict_survival` | deterministic runtime evidence | `DEEPSEEK_API_KEY` unset、`--with-llm`なし |
| `bash scripts/evidence_validate.sh --require-verified <bundle>` | produced bundle validation | pathを実行時artifactへ限定 |

`evidence_run.sh`と共通libraryは、temporary/run directoryのprefix、symlink、lock ownershipを検査し、cleanupの`rm -rf`対象を限定している。ただしこれは上流自身の防御であり、独立Acceptance Evidenceではない。

### 10.2 Forbidden in GA-002

| Script/path | Reason |
|---|---|
| `scripts/story.sh`、manual LLM workflow | external paid APIとsecretを使用 |
| `scripts/quickcheck.sh` | `pkill -9 -f`でhost上のGradle/runServer/Loom processを広くkillし、固定pathを削除 |
| `scripts/prod_test.sh` | `run-prod/mods/*.jar`とworld内bot stateを削除し、Fabric API JARをchecksumなしでdownload |
| `scripts/harness_probe.sh` | 固定`/tmp` path、弱いcleanup、旧run entrypoint |
| `scripts/auto30.sh`、`scripts/reliability.sh`、`scripts/gate.sh` | 長時間・反復・shared processへの影響がありbaseline最小再現に不要 |
| mining acceptance/shard/aggregate/release scripts | 長時間・多数run。GA-002のbaseline範囲を超える |
| `scripts/pin_baseline.sh` | repositoryのbaseline index/reportを変更する |
| `scripts/capability_matrix.sh --output ...` | tracked documentationを変更する |
| upstream GitHub workflows | mutable action tagを含み、自分たちの実行境界ではない |

`food_test.sh`や`night_watch.sh`などwrapper scriptは単体で必要ない。GA-002では上記allowlist以外を実行しない。

## 11. GA-002 execution contract

1. Linux semanticsを持つdisposable directoryまたはephemeral runnerを使う。Windows PowerShellからshell scriptを直接実行しない。
2. fixed SHAを取得し、`git rev-parse HEAD`とtreeのclean状態を記録する。
3. repository hooksを使用せず、submoduleとsymlinkがないことを再確認する。
4. wrapper JAR SHA-256を本書の値と照合する。
5. Gradle 9.4.0 distributionを公式SHA-256と照合する。
6. project専用の`GRADLE_USER_HOME`、`TMPDIR`、server run directoryを使用する。
7. inherited environmentをallowlist化し、全API key/token/credentialを除外する。特に`DEEPSEEK_API_KEY`をunsetする。
8. 上記allowlist commandを一つずつ実行し、exit code、duration、network prerequisite、artifactを記録する。
9. 上流source、fixture、assertion、config defaultを変更しない。
10. PASS、FAIL、UNVERIFIED、NOT RUNを別々に記録する。

GA-002の実行は第三者codeの任意code executionである。可能ならcontainer/VM/ephemeral runnerを使い、host homeや他repositoryをmountしない。

## 12. Stop conditions

次のいずれかが起きたら即時停止し、GA-002をFAIL/BLOCKEDとして記録する。

- fixed SHA、tree、wrapper、Gradle distribution hashの不一致
- credential、login、paid API、elevated privilegeの要求
- allowlist外domainまたは説明不能なnetwork destinationへの接続
- isolated checkout、専用cache、専用temp以外へのwrite/delete
- host processへのglobal kill
- repository source、fixture、assertionの変更
- symlink/submodule/binaryが監査時と異なる
- cleanup guardの拒否、unbounded child process、timeout後に残るserver process
- log/artifactにcredential patternまたはprivate dataが残る

## 13. Evidence and redaction

GA-002は次を保存する。

- upstream SHAと`minecraft-ai` SHA
- OS/JDK/Gradle/runtime version
- commandとexit code、開始・終了時刻、duration
- result summary、manifest、checksums
- artifactの保存先とretention
- failure logの必要最小限の抜粋

大容量artifactとraw server logをGitへ直接commitしない。GitHub artifact等へ置く場合も、API key、environment dump、home path、player/private chatを検査・redactする。

## 14. Unresolved risks

- commitにverified signatureがない
- Gradle distribution checksumがpropertiesへ固定されていない
- dependency lockとartifact verification metadataがない
- external Gradle plugins/dependenciesのtransitive codeを静的監査していない
- workflow actionがcommit SHAでpinされていない
- upstream harnessと実装が同一設計主体であり、body採否の独立証拠ではない
- `online-mode=false` serverの結果を実運用認証環境へそのまま一般化できない

これらはGA-002の隔離とGA-003のEvidence Independence評価で扱う。GA-000の条件付き承認は、body採用を意味しない。

## 15. Finding

固定SHAは、MIT License、submodule/symlinkなし、公式一致するGradle wrapper JAR、比較的防御的なevidence cleanupを備える。一方で、unsigned commit、dependency integrity metadata不足、危険なlegacy helper script、mutable workflow action tagがある。

したがって、repositoryを一般的に信用するのではなく、**秘密情報のないdisposable Linux環境でallowlist commandだけを実行する**条件でGA-002へ進める。`quickcheck.sh`、`prod_test.sh`、LLM/長時間/書換え系scriptは査定対象から除外する。
