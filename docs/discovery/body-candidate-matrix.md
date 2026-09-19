# Gate A body candidate matrix

Issue: [GA-003](https://github.com/blancaile/minecraft-ai/issues/6)

調査日: 2026-09-19 (Asia/Tokyo)

## 1. Finding

3候補のどれも、現時点でGate A bodyとしてそのまま採用できる証拠はない。

- `mc_aiplayer`は、server-side fake player、task/goal、永続化、recovery、evidenceを一体で持つ唯一の候補である。しかし自然地形の長距離navigationは固定されたlegacy batchで`0/4`、bread chainは`1/5`であり、再現可能な現行Gate A evidenceは存在しない。内部結合も強い。
- Mineflayerは、外部client botとして観測・移動・inventory・craft・dig/buildのprimitiveと拡張可能なpathfinderを持つ。しかしmission semantics、restart reconciliation、権限境界、独立evidenceは上位層として新設する必要がある。online-mode serverではMicrosoft accountの運用も増える。
- Carpetは、追加accountなしのserver-side fake playerとplayer action commandを提供する最小substrateとして強い。しかしnavigation、mission、resource chain、recovery、evidenceはほぼ新規実装になる。

従ってGA-004で決めるべきことは「完成品の選択」ではなく、どの既存境界までを信用してM1の検証対象にするかである。本Issueでは採用判断を行わない。

## 2. Scope and evidence policy

評価軸は[Gate A Intent Contract](../gates/gate-a-intent.md)の9 capabilityである。scenario数、timeout、recovery budget、thresholdはGA-005まで確定しない。

### Status

| Status | 意味 |
|---|---|
| `REUSE` | 要件に対する実装と十分な証拠があり、境界を保った再利用候補 |
| `EXTEND` | 有用な実装はあるが、Gate A semanticsまたは証拠の追加が必要 |
| `MISSING` | 候補本体に必要な実装がない |
| `BLOCKED` | 既知の失敗または前提不足により、現状ではGate Aへ進めない |
| `UNVERIFIED` | 実装の存在は確認できるが、要件に対応する信頼可能な証拠がない |

### Evidence independence

| 値 | 意味 |
|---|---|
| `UPSTREAM_SELF_TEST` | 候補自身のrunner、fixture、assertionで得た証拠。こちらで再実行しても独立black-boxには数えない |
| `OUR_BLACK_BOX` | 候補の内部成功申告に依存せず、外部controllerがworld/postconditionを検証した証拠 |
| `BOTH` | 両方が存在する |
| `NONE` | 本調査で利用できる要件対応証拠がない |

`OUR_BLACK_BOX_VERIFY`は、M1での独立検証の構築可能性を`possible / difficult / impossible`で示す。`possible`は実施済みを意味しない。本調査では独立Acceptance Harnessを実装していないため、全候補で`OUR_BLACK_BOX`はまだ存在しない。

## 3. Candidate snapshots

| Candidate | Observed revision | Runtime boundary | Account | License | Local execution |
|---|---|---|---|---|---|
| `mc_aiplayer` | [`a029fa6`](https://github.com/zoyluoblue/mc_aiplayer/tree/a029fa6a3760fd0f83834c104051b041d986da60) | Fabric server mod / in-process `ServerPlayerEntity` | 外部account不要 | MIT | GA-002で固定SHAを実行 |
| Mineflayer | [`2084d0e`](https://github.com/PrismarineJS/mineflayer/tree/2084d0e6e0224fac30ba55d9cae7cfcd17cc9d65) + pathfinder [`5872016`](https://github.com/PrismarineJS/mineflayer-pathfinder/tree/5872016d3251050b119c4d4c903bccd2d05f62df) | Node.jsの独立Minecraft protocol client | offline-modeは不要。online-modeはMicrosoft login/token管理 | MIT | 文書・sourceのみ。probeなし |
| Carpet fake player | [`199efb1`](https://github.com/gnembon/fabric-carpet/tree/199efb19a9bc327bbea5cfed4209d9b0762aa865) | Fabric server mod / in-process fake player | 外部account不要 | MIT | 文書・sourceのみ。probeなし |

MineflayerとCarpetのrevisionは比較調査時点を固定する参照であり、build可否を再現したpinではない。

## 4. Executive comparison

| Concern | `mc_aiplayer` | Mineflayer | Carpet fake player |
|---|---|---|---|
| player lifecycle | 実装、unit/GameTest、restart self-testあり | login/spawn/death/kick eventsはあるがResident lifecycleは上位実装 | fake player spawn/action/killあり。Resident lifecycleは上位実装 |
| observation | server stateへ直接アクセスするcollectorあり | entity/block/inventory/health APIあり | server/Scarpet APIで取得可能。body用snapshotはなし |
| navigation | 独自A*とrecoveryあり。ただし自然地形120-block baselineは`0/4` | pathfinder pluginにA*、goal、replan、dig/place、long-distance API | player actionのみ。autonomous pathfinderなし |
| inventory / craft / mining | 一体化したaction/task/recipe/mining chainあり | core APIとpluginでprimitiveあり | player action/Scarpetから組めるがchainなし |
| mission / restart | goal/task/checkpoint/persistenceあり。GA-002二JVM self-testはPASS | application側で新設 | app/mod側で新設 |
| safety / authority | operating profile/capability gateあり。多数のruntime singletonと結合 | protocol clientをserver権限外に置けるが、region/capability policyは新設 | command permissionはあるがmutation boundaryは新設 |
| evidence | immutable bundle/validator/self-testあり | library testはあるがGate A evidence schemaなし | project testはあるがGate A evidence schemaなし |
| black-box control | command起動可能。server/world観測を別実装すれば可能 | 外部process制御とserver側observerの組合せで可能 | command起動とserver/world観測で可能 |
| main coupling | bodyからbrain/memory/mining/evidenceまで同一runtime | Node.js process、protocol/version、plugin graph、account | Fabric/Carpet version、server command/Scarpet |
| portability | 低〜中: Minecraft/Fabric internalsと専用型へ密結合 | 中〜高: server実装から分離。ただしprotocol/version依存 | 中: Fabric server内。Carpet API/command依存 |

## 5. Requirement matrix — `mc_aiplayer`

共通前提: GA-002でJUnit 351件とGameTest 587件、persistence restart、strict evidence 9/9を固定SHAで再現した。これはすべてupstreamのfixture/runner/assertionであり、独立black-box evidenceではない。詳細は[GA-002 result](pinned-baseline-results.md)を参照。

| Requirement | Candidate | Existing implementation | Existing upstream test | Existing upstream evidence | Our black-box verification | Evidence independence | Status | Coupling cost | Portability | Expected modification area | Operational risk | Required work |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Lifecycle integrity | `mc_aiplayer` | manager、fake connection、respawn、persistence、runtime lifecycle | lifecycle/persistence/GameTest | GA-002 restart self-test PASS。death/restart全体の外部証明ではない | `possible`: server restartとplayer/world状態を外部観測 | `UPSTREAM_SELF_TEST` | `EXTEND` | high | low | manager、persistence、lifecycle | in-process crash影響、death処理の特殊化、singleton cleanup順 | restart/death/despawnの外部postconditionとcorruption検査 |
| Observation integrity | `mc_aiplayer` | perception snapshot、world query、inventory/structure predicates | deterministic testsあり | 587 GameTest内のcomponent evidence。自然worldでのfreshness/completenessは未証明 | `difficult`: 内部snapshotと別server observerの差分比較が必要 | `UPSTREAM_SELF_TEST` | `UNVERIFIED` | high | low | perception、goal predicates、world query | hidden server accessやstale snapshotが成功判定へ混入 | 観測sourceを列挙し、black-box world truthとの差分test |
| Locomotion and reachability | `mc_aiplayer` | A*、path executor、walk controller、stuck/safety watcher | pathfinding/GameTestあり | legacy `navigate_120=0/4`; tested revision/seed/config不明、confidence LOW | `possible`: 外部座標・block mutation・terminal reasonを観測 | `NONE` | `BLOCKED` | high | low | pathfinding、movement、nav recovery | silent stall、過剰dig/place、未到達の誤完了 | 固定seed自然地形navigation、stall budget、mutation boundaryをM1化 |
| Interaction correctness | `mc_aiplayer` | gather/pickup/container/craft/smelt/build/mine actions | 多数のaction/task GameTest | controlled scenarioとcomponent testはPASS。mission-level外部postconditionなし | `possible`: inventory/container/world deltaを外部検査 | `UPSTREAM_SELF_TEST` | `EXTEND` | high | low | action、craft、task、goal verifier | task successとworld resultの乖離、partial mutation | representative chainを外部stateでassertし、false successを注入test |
| Resource lifecycle | `mc_aiplayer` | resource acquisition、tool/craft/smelt、inventory pressure対応task | deterministic task/mining tests | natural legacy: food `8/10`, bread `1/5`, iron armor `10/12`, diamond `6/10`; 全てUNVERIFIED/LOW | `possible`: declared empty inventoryから最終inventory/worldを検査 | `NONE` | `EXTEND` | high | low | goal/task/mining/craft/inventory | 長鎖でrecoveryが膨張、fixture依存、resource duplication/loss | Gate A代表chainを現行SHA・固定seed・strict modeで再測定 |
| Construction integrity | `mc_aiplayer` | blueprint/build action、structure verifier、terrain handling | build edge/GameTestあり | legacy hut `7/10`だがassertionは近傍の板80個で、構造完成を証明しない | `possible`: server側でexpected block volumeと余計なmutationを比較 | `NONE` | `EXTEND` | high | low | build task/action、blueprint、structure verifier | 弱いassertion、置換・整地による範囲外mutation | 固定構造の正負space assertionとauthorized region検査 |
| Recovery and reconciliation | `mc_aiplayer` | checkpointable tasks、stuck/death recovery、restart resume、intent control | recovery/death/restart GameTest | GA-002 restart self-test PASS、cancel/replace controlled suite PASS | `difficult`: failure injectionと内部checkpoint非依存のtruth oracleが必要 | `UPSTREAM_SELF_TEST` | `EXTEND` | high | low | goal executor、task manager、persistence、watchers | recovery loop、stale lease、fallbackによる原因隠蔽 | failure injection、bounded recovery、world reconciliationを外部検証 |
| Safety and authority | `mc_aiplayer` | strict profile、capability gate、authorization、pause/cancel/quarantine相当のcontrol | capability/cancel/replace tests | GA-002 privileged flags false、control scenario PASS | `difficult`: 許可範囲外の全mutationを別observerで収集 | `UPSTREAM_SELF_TEST` | `EXTEND` | high | low | auth、mode、intent controller、全mutation action | profile bypass、未列挙mutation、emergency teleport等の特権fallback | actor/target/region/capability policyとnegative mutation audit |
| Inspectability | `mc_aiplayer` | structured log、replay/profiler、manifest、validator | validator self-test、evidence tests | GA-002 immutable VERIFIED bundleを再現 | `possible`: 外部event collectorとworld truthを突合 | `UPSTREAM_SELF_TEST` | `EXTEND` | medium-high | medium | log/evidence schema、task terminal reporting | tick内`NullPointerException`をlog後にswallowし継続する実装、self-reported success | common external event schema、failure causality、silent retry/stall detector |

### `mc_aiplayer` coupling finding

fake playerだけを切り出す境界は薄くない。[`AIPlayerManager`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/src/main/java/io/github/zoyluo/aibot/manager/AIPlayerManager.java)はpersistence、memory、capability、pathfinding、runtime lifecycleへ直接依存し、[`RuntimeLifecycleCoordinator`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/src/main/java/io/github/zoyluo/aibot/runtime/RuntimeLifecycleCoordinator.java)はbrain、goal、task、memory、mining evidence、network、observationをglobal singleton順序で制御する。従って「bodyだけを依存ライブラリとして追加」は現状のsource boundaryと一致しない。

さらに[`AIPlayerEntity.tick`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/src/main/java/io/github/zoyluo/aibot/entity/AIPlayerEntity.java)が`NullPointerException`を記録して処理を継続するため、failure visibilityとstate integrityを独立試験で確認する必要がある。

## 6. Requirement matrix — Mineflayer

比較はMineflayer coreと公式`mineflayer-pathfinder`に限定する。community pluginを組み合わせれば広がる可能性はあるが、未選定のplugin能力を既存evidenceには数えない。

| Requirement | Candidate | Existing implementation | Existing upstream test | Existing upstream evidence | Our black-box verification | Evidence independence | Status | Coupling cost | Portability | Expected modification area | Operational risk | Required work |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Lifecycle integrity | Mineflayer | protocol login、spawn/death/kick/end events | core integration/unit testあり | Gate A Resident restart evidenceなし | `possible`: process/server再起動とworld/player stateをserver側観測 | `NONE` | `EXTEND` | medium | high | supervisor、identity、state store | reconnect loop、token/account、server/client version | lifecycle FSM、durable state、restart reconciliationを新設 |
| Observation integrity | Mineflayer | entity/block/world/inventory/health API | core API testsあり | Gate A freshness/completeness evidenceなし | `possible`: client viewとserver truthを比較 | `NONE` | `EXTEND` | medium | high | observation adapter、snapshot schema | unloaded chunk、protocol latency、client-only visibility | consistency contractとunknown/stale表現を新設 |
| Locomotion and reachability | Mineflayer | pathfinder A*、goal、replan、dig/place、swim、long-distance | pathfinder test suiteあり | project READMEの機能主張のみ。Gate A success batchなし | `possible`: server座標・terrain delta・terminal reasonを観測 | `NONE` | `EXTEND` | medium | high | movements policy、recovery wrapper | plugin README自身がdeep changes継続中と明記、door等の既知制約 | fixed-seed navigationとbounded stuck/replan policy |
| Interaction correctness | Mineflayer | inventory、craft、container、dig、place、attack/use API | core integration testsあり | mission-level postcondition evidenceなし | `possible`: server/world/inventory deltaで検査 | `NONE` | `EXTEND` | medium | high | action adapter、transaction semantics | packet/server timing、GUI state、partial action | typed action resultとpostcondition verifierを新設 |
| Resource lifecycle | Mineflayer | primitiveとcollectblock等のplugin候補 | primitive testはある | end-to-end resource chain evidenceなし | `possible`: empty inventoryからserver-side postconditionを検査 | `NONE` | `MISSING` | medium-high | medium-high | planner/task/inventory policy | plugin間競合、長鎖recovery、dependency drift | mission/task/resource FSMを新設 |
| Construction integrity | Mineflayer | dig/placeとbuilder候補 | primitive testはある | fixed structureのGate A evidenceなし | `possible`: server block volumeを比較 | `NONE` | `MISSING` | medium-high | medium-high | blueprint executor、material/reachability policy | partial build、scaffold residue、範囲外破壊 | fixed blueprint missionとstructure verifierを新設 |
| Recovery and reconciliation | Mineflayer | pathfinder event/error、client events | component testsのみ | bounded mission recovery/restart evidenceなし | `difficult`: process kill、disconnect、death injectionとtruth oracle | `NONE` | `MISSING` | high | medium | checkpoint、recovery、reconcile、supervisor | reconnect後の二重実行、lost action、stale client state | durable mission journalとidempotent reconciliationを新設 |
| Safety and authority | Mineflayer | server上は通常player権限。path movement cost/exclusion設定あり | component testsのみ | region/capability boundary evidenceなし | `possible`: server pluginで全mutationをaudit | `NONE` | `MISSING` | medium-high | high | policy enforcement、server observer | client側policy bypass、account compromise、anti-bot policy | server-enforced actor/region/capability gateを新設 |
| Inspectability | Mineflayer | events/debug output、viewer | library testsあり | canonical trace/evidence bundleなし | `possible`: client eventとserver truthを共通IDで収集 | `NONE` | `MISSING` | medium | high | event schema、artifact writer、validator | client/server clock差、errorのPromise吸収 | terminal/event schemaとindependent evidence pipelineを新設 |

公式READMEは観測・physics・inventory・craft・dig/build等を列挙し、[pathfinder](https://github.com/PrismarineJS/mineflayer-pathfinder/blob/5872016d3251050b119c4d4c903bccd2d05f62df/readme.md)はA*、long-distance、dynamic replanning、dig/placeを提供する。一方、[Mineflayerのlogin例](https://github.com/PrismarineJS/mineflayer/blob/2084d0e6e0224fac30ba55d9cae7cfcd17cc9d65/README.md#getting-started)ではonline-modeにMicrosoft authとtoken cacheが必要である。

## 7. Requirement matrix — Carpet fake player

比較対象はFabric Carpet coreのfake playerとScarpet/command surfaceである。Scarpet app storeの個別app能力は数えない。

| Requirement | Candidate | Existing implementation | Existing upstream test | Existing upstream evidence | Our black-box verification | Evidence independence | Status | Coupling cost | Portability | Expected modification area | Operational risk | Required work |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Lifecycle integrity | Carpet | `/player ... spawn/kill`、server-side fake player | project testsはあるが要件対応不明 | Resident restart evidenceなし | `possible`: commandとserver stateを観測 | `NONE` | `EXTEND` | low-medium | medium | identity、persistence、lifecycle wrapper | Carpet/Minecraft version、world reload時のapp state | durable identityとrestart lifecycleを新設 |
| Observation integrity | Carpet | server/Scarpetのentity・block query | API/project tests | body snapshot integrity evidenceなし | `possible`: 同一server内の別observerを用意 | `NONE` | `MISSING` | medium | medium | observation adapter、snapshot schema | bodyとoracleが同一権限境界になりやすい | restricted observation surfaceと外部oracleを新設 |
| Locomotion and reachability | Carpet | forward/back/jump/look等のplayer action | action implementation/testはある | autonomous navigation evidenceなし | `possible`: 座標とworld deltaを観測 | `NONE` | `MISSING` | high | medium | pathfinder、executor、stuck/replan | actionだけではterrain reachabilityを解けない | navigation stack全体を新設または別component統合 |
| Interaction correctness | Carpet | use/attack/drop等のplayer action | project component tests | mission-level postcondition evidenceなし | `possible`: inventory/world deltaをserver側検査 | `NONE` | `EXTEND` | medium | medium | typed action adapter、result semantics | command成功とgame postconditionの乖離 | action resultとpostcondition verifierを新設 |
| Resource lifecycle | Carpet | player primitiveのみ | 要件対応testなし | resource chain evidenceなし | `possible`: world/inventoryを検査 | `NONE` | `MISSING` | high | medium | task/craft/inventory/resource planner | ほぼcustom body実装になる | resource mission stack全体を新設 |
| Construction integrity | Carpet | use/attackによるblock操作primitive | 要件対応testなし | construction evidenceなし | `possible`: block volumeを検査 | `NONE` | `MISSING` | high | medium | navigation、blueprint、material、verifier | reachability・材料・partial rollbackを全て負担 | construction stack全体を新設 |
| Recovery and reconciliation | Carpet | app unload時のstate保存hook等 | API/project tests | mission checkpoint/recovery evidenceなし | `difficult`: app/server restartとfailure injectionが必要 | `NONE` | `MISSING` | high | medium | mission journal、recovery、reconcile | duplicated action、app stateとworld divergence | durable mission runtime全体を新設 |
| Safety and authority | Carpet | Scarpet command permission、server command boundary | permission/project tests | actor/target/region/capability evidenceなし | `possible`: command/mutation auditを別modで収集 | `NONE` | `EXTEND` | medium | medium | permission、region policy、mutation audit | console/op権限が広すぎる、Scarpet command実行権限 | least-privilege commandとserver-enforced mutation policy |
| Inspectability | Carpet | command output、server log、Scarpet hooks | project tests | mission trace/evidence bundleなし | `possible`: server event observerを追加 | `NONE` | `MISSING` | medium-high | medium | event schema、artifact writer、validator | command logだけではphase/retry/causality不足 | common traceとindependent evidence pipelineを新設 |

[`PlayerCommand`](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/src/main/java/carpet/commands/PlayerCommand.java)はspawn、kill、stop、use、attack、mount、look、turn、move等を提供する。[Scarpet Entities API](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/docs/scarpet/api/Entities.md)も`fake`をCarpet-spawned fake playerとして区別する。これらはbody substrateの証拠であり、自律mission bodyの証拠ではない。

## 8. Gap register for M1 planning

GA-004/005で採用戦略が決まった後、次をM1候補へ変換する。本Issueでは実装しない。

| Gap | Candidate-independent outcome | Priority signal |
|---|---|---|
| independent control/observer boundary | body内部のsuccess判定に依存せずmissionを開始・観測できる | Gate A全行の前提 |
| external postcondition oracle | position、inventory、container、world structure、mutation範囲を判定 | false success防止 |
| deterministic fixture/reset | seed、initial inventory、world stateを再現しrun間を隔離 | evidence比較可能性 |
| bounded terminal semantics | `COMPLETED/FAILED/CANCELLED/PARTIAL`とstall/retry budget | 無限retry防止 |
| lifecycle/failure injection | death、disconnect、process/server restart、chunk/world lifecycle | reconciliation証明 |
| evidence artifact schema | command、events、world delta、terminal reason、checksums | 監査・再現性 |
| natural-terrain navigation gate | obstacle、高低差、unreachable、long distance、mutation boundary | `mc_aiplayer`最大の既知blocker |
| representative resource/build chains | acquisition→carry→store/craft/useと固定construction | primitive成功との分離 |
| authority negative tests | unauthorized actor/target/region/capabilityを拒否 | world保全 |

## 9. Decision impact

- `mc_aiplayer`を選ぶ場合、M1の中心は「不足機能の追加」より先に、既存の一体runtimeを独立black-boxで囲い、自然terrainのnavigationと長鎖missionを反証可能にすることである。
- Mineflayerを選ぶ場合、primitive再実装は少ないが、Resident mission/persistence/safety/evidence control planeは新規product codeになる。
- Carpetを選ぶ場合、fake-player lifecycleは最小で済むが、bodyの大半をcustom実装する計画として扱う必要がある。
- `mc_aiplayer`の強いself-testは資産だが採用根拠の十分条件ではない。Mineflayer/Carpetの豊富なAPIも同様にGate A evidenceではない。

## 10. Primary sources

### `mc_aiplayer`

- [Capability matrix at fixed SHA](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/docs/CAPABILITY_MATRIX.md)
- [Testing and evidence](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/docs/TESTING_AND_EVIDENCE.md)
- [`AIPlayerManager`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/src/main/java/io/github/zoyluo/aibot/manager/AIPlayerManager.java)
- [`RuntimeLifecycleCoordinator`](https://github.com/zoyluoblue/mc_aiplayer/blob/a029fa6a3760fd0f83834c104051b041d986da60/src/main/java/io/github/zoyluo/aibot/runtime/RuntimeLifecycleCoordinator.java)

### Mineflayer

- [Mineflayer README at observed revision](https://github.com/PrismarineJS/mineflayer/blob/2084d0e6e0224fac30ba55d9cae7cfcd17cc9d65/README.md)
- [Mineflayer API](https://github.com/PrismarineJS/mineflayer/blob/2084d0e6e0224fac30ba55d9cae7cfcd17cc9d65/docs/api.md)
- [Mineflayer pathfinder README at observed revision](https://github.com/PrismarineJS/mineflayer-pathfinder/blob/5872016d3251050b119c4d4c903bccd2d05f62df/readme.md)

### Carpet

- [Fabric Carpet README at observed revision](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/README.md)
- [`PlayerCommand`](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/src/main/java/carpet/commands/PlayerCommand.java)
- [Scarpet Entities API](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/docs/scarpet/api/Entities.md)
- [Scarpet overview and command permission](https://github.com/gnembon/fabric-carpet/blob/199efb19a9bc327bbea5cfed4209d9b0762aa865/docs/scarpet/api/Overview.md)
