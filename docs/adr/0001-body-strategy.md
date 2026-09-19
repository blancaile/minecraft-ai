# ADR-0001: Minecraft body strategy

- Status: Accepted — time-boxed `DEFER`
- Date: 2026-09-19
- Issue: [GA-004](https://github.com/blancaile/minecraft-ai/issues/7)
- Decision owner: `blancaile/minecraft-ai`

## Context

Gate Aは、Jev、DeepSeek、会話、記憶より先に、Minecraft内のbodyがdeterministic missionを安全に完了・失敗・回復できることを証明する境界である。

M0で得たEvidenceは次の通り。

- [Gate A Intent](../gates/gate-a-intent.md)は、lifecycle、observation、locomotion、interaction、resource lifecycle、construction、recovery/reconciliation、safety/authority、inspectabilityを要求する。
- [`mc_aiplayer` supply-chain audit](../discovery/mc-aiplayer-supply-chain-audit.md)は、固定SHAを限定commandで調査可能としたが、dependency verification不足、mutable workflow action、破壊的script等のriskを確認した。
- [Pinned baseline reproduction](../discovery/pinned-baseline-results.md)では、固定SHAのbuild、351 JUnit、587 GameTest、restart self-test、controlled evidence 9/9を再現した。ただしrunner、fixture、assertionは全てupstream由来で、独立black-box evidenceではない。
- [Body candidate matrix](../discovery/body-candidate-matrix.md)では、3候補のどれにも独立Gate A evidenceがない。`mc_aiplayer`は唯一の統合body候補だが、legacy natural navigationは`navigate_120=0/4`、bread chainは`1/5`、hutは弱いassertionで`7/10`、実装はbodyからbrain/memory/evidenceまで強く結合する。

この時点でimport方式を決めると、候補自身のself-testを採用根拠と誤認し、大きなcode ownershipを先に引き受ける。反対に即REJECTすると、再現済みのfake-player、task、persistence、recovery、evidence資産を独立評価せず捨てる。

## Decision

**Decision: `DEFER`**

`mc_aiplayer`をleading candidateとして保持するが、採用、依存追加、submodule/subtree、source import、fork、selective portを開始しない。M1の最初のdecision trancheで、candidate-neutralな最小black-box harnessから固定SHAを評価し、その結果だけで`EXTEND / PERMANENT_FORK / SELECTIVE_PORT / REJECT`のいずれかへ一度だけ移行する。

これはupstream改善待ちではない。必要な外部変化は**なし**であり、不足しているのは自分たちが所有する独立evidenceである。

## Time box and expiry

再評価期限は、次の早い方とする。

1. GA-005で定義するM1 body-decision trancheの全Issue完了時
2. trancheの最初の実装commitからactive engineering 10日
3. 2026-10-31 23:59 JST

期限までに移行Decisionを記録できなければ、`mc_aiplayer`はM1 body baseとして**自動的に`REJECT`**とする。DEFERの延長は新しい独立Evidenceまたは明示的な外部変更がある場合だけ、新ADRで行う。単なる未着手、工数不足、既投資は延長理由にしない。

## Re-evaluation contract

GA-005が数値とscenarioを確定するため、ここではacceptance thresholdを先取りしない。再評価に必要なのは、少なくとも次のEvidenceである。

- fixed source SHA、build dependency hash、effective config、seedを持つrun
- body内部のterminal申告ではなく、別observerが確認したworld/player/inventory postcondition
- lifecycle/start-stop、natural-terrain navigation、interaction/resource chain、restart reconciliation、authority negative caseを含むdecision subset
- stall、retry、recovery、failure reason、unauthorized mutationを外部から判別できるartifact
- unchanged fixed SHAの結果と、必要なら最小patch後の結果を分離した比較
- 変更候補のpackage/file inventoryと、upstream更新を取り込む際の回帰面積

Harnessは候補固有classやlog messageを成功oracleにしない。候補固有adapterはcommand発行と観測値の正規化に限定する。

## Pivot rules

次の順序で一つを選ぶ。

| Target decision | 検証可能なtrigger |
|---|---|
| `EXTEND` | 固定SHAがGate A v1 decision subsetを満たし、必要変更が外部adapter、設定、公開extension seamに限定され、core body/task/pathfinding/persistenceのpatchを要しない |
| `PERMANENT_FORK` | fixed SHAのbody foundationはGate A v1を概ね満たすがcore patchが不可避であり、fork全体のtest/evidenceを継承して保守する方がselective extractionより小さい。NPE swallow等のfail-open behaviorを修正・回帰検査できるownership計画がある |
| `SELECTIVE_PORT` | Gate Aを満たすcomponent境界が特定でき、移植対象とtransitive dependencyが明示され、移植後に独立testで同等性を証明できる。full forkより所有codeとupstream追従面積が小さい |
| `REJECT` | Gate A v1 mandatory caseの重大failure、unauthorized mutation、再現不能なstall、world/save corruption、black-box観測不能、または期限超過がある。あるいは修正・抽出面積が候補利用の便益を失わせる |

`EXTEND`を既定の成功先にしない。複数triggerを満たす場合は、所有code、回帰面積、upstream追従面積が最小の案を選び、同点なら可逆性が高い案を選ぶ。

## Options considered on common evidence axes

| Option | Capability coverage | Independent evidence | Coupling / ownership | Supply-chain / maintenance | Reversibility | M0 judgment |
|---|---|---|---|---|---|---|
| `EXTEND` | `mc_aiplayer`が最も広い | なし。self-testのみ | 公開された薄いextension seamが見えず、runtime singletonと専用型へ強く結合 | upstream build/sourceへ依存しつつlocal adapterも保守 | 中 | 今は選べない。black-box合格とcore patch不要を要証明 |
| `PERMANENT_FORK` | 全機能と587 GameTestを保持可能 | なし。forkしても独立性は増えない | 最大。brain/memory/LLMを含むrepository全体を所有 | upstream監視、backport、Fabric/Minecraft更新、security修正を恒久負担 | 低 | 証拠前のforkはsunk costが大きすぎる |
| `SELECTIVE_PORT` | 必要部分だけ選べる | port後に再証明が必要 | manager/lifecycle/task/pathfinding/persistenceのtransitive couplingが広い | provenanceとpatch追跡をcomponentごとに維持 | 中 | 現source境界では抽出量をまだ限定できない |
| `REJECT` | 既存統合資産を失う | false confidenceは除去できる | custom bodyまたは別候補を全面所有 | 初期費用最大だが境界は自分で設計可能 | 高 | 正常な結論。ただし現時点では未実施black-boxで判断が早い |
| `DEFER` | 候補を変更せず比較可能 | 不足Evidenceを先に作る | import前なのでownershipを限定 | time box中はupstream codeを保守しない | 高 | 採用を前提化せず、次の不可逆判断に必要な情報を得る |

## Ownership boundary during DEFER

`blancaile/minecraft-ai`が所有するもの:

- Gate A contract、scenario、fixture contract
- candidate-neutral controller/observer interfaces
- evidence schema、artifact validator、decision report
- candidate adapterのうちcommand発行・観測正規化だけ
- M1 Issue、test result、ADR

所有しないもの:

- `mc_aiplayer` sourceまたはその派生物
- upstreamのbrain、memory、DeepSeek client、story/LLM workflow
- upstream testのassertionを独立oracleとして再利用したもの
- MineflayerまたはCarpetのproduction integration

M1 decision trancheで作るharness codeは、それ自体をResident production architectureへ昇格させない。昇格には別IssueとADRが必要である。

## Provenance and license obligations

DEFER中は第三者sourceをrepositoryへ取り込まない。fixed SHA、取得元、tree/file hash、licenseをEvidence manifestへ記録する。

後続Decisionでsourceまたはbinaryを取り込む場合は、少なくとも次を必須とする。

- MIT license textと既存copyright noticeの保持
- upstream repository URL、commit SHA、取得日、未変更/変更の区別
- 変更fileとlocal patchの追跡
- source/binary/dependencyのchecksumまたはlock
- `PERMANENT_FORK`では到達可能なgit historyを保持
- `SELECTIVE_PORT`ではfile単位のoriginとcommitをheaderまたはprovenance manifestへ記録

ライセンス適合は品質・security・compatibilityを保証しないため、Evidence gateとは別に扱う。

## Upstream observation and backport policy

DEFER中は、採用前提の定期mergeや自動追従を行わない。再評価開始時に固定SHA以後のrelease、security fix、Gate A関連変更だけを観測し、評価対象SHAを変える場合はGA-000相当の差分auditを行う。

`PERMANENT_FORK`へ移行した場合、upstream変更はissue単位でreviewし、直接mergeせず、provenanceを残したcherry-pickまたは再実装と独立Gate回帰を行う。`SELECTIVE_PORT`ではorigin file/commitごとに差分を監視する。無関係なLLM/story機能はbackport対象外とする。

## Consequences

### Positive

- 自分たちのcontractとoracleを候補の実装都合から分離できる。
- fork/import前に自然terrain navigation、long-chain、restart、authorityの弱点を検出できる。
- `REJECT`を失敗ではなく、期限とEvidenceで到達する正常なDecisionにできる。
- 同じharnessをMineflayer、Carpet、将来のcustom body比較に再利用できる。

### Negative

- M1の最初にbody機能ではなく評価基盤を作る時間が必要になる。
- candidate adapterが完全に中立にならない可能性がある。
- fixed SHAが失敗した場合、強いupstream self-test資産を使わずに終わる可能性がある。

## Unresolved risks

- GA-005でscenarioを広げすぎるとdecision tranche自体がmini-productになる。
- 同一Minecraft server内observerでは、bodyとoracleが同じbugや特権を共有し得る。
- natural terrainのseed選択が候補に有利または不利へ偏る可能性がある。
- Mineflayer/Carpetを同量probeしないため、`mc_aiplayer` REJECT後には追加Discoveryが必要になり得る。
- wall-clock期限は作業停止でも到来する。期限超過は自動採用ではなく安全側のREJECTへ倒す。

## Follow-up

GA-005でGate A v1と、次の順序を持つM1 backlogを確定する。

1. candidate-neutral black-box contract and artifact schema
2. deterministic fixture/controller/observer MVP
3. unchanged `mc_aiplayer` fixed-SHA decision run
4. coupling/patch inventory only if the unchanged candidate fails in a potentially repairable way
5. ADR-0001 superseding decision: `EXTEND / PERMANENT_FORK / SELECTIVE_PORT / REJECT`
