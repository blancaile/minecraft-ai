# Gate A Intent Contract

> **NOT FINAL ACCEPTANCE CONTRACT**
>
> この文書はGate Aで何を証明したいかを固定する。scenario数、timeout、recovery budget、測定方法、数値thresholdは候補査定後のGA-005で決定する。この文書だけでbody候補の合否を判定してはならない。

状態: M0 intent baseline

関連Issue: [GA-001](https://github.com/blancaile/minecraft-ai/issues/3)

## 1. Purpose

Gate Aは、AI認知、人格、会話、記憶を評価する前に、Minecraft内の身体とtask実行基盤がResident開発の土台になり得るかを証明するための門である。

中心となる問いは次である。

> 一時的な失敗や環境変化を含む複数段階のmissionを、無許可の特権操作や人間の救済に依存せず、観測可能で有限な回復を通じて最終状態まで完遂できるか。

Gate Aで評価するのは特定OSSへの適合ではない。候補の選択、拡張、fork、部分移植、棄却、保留のいずれにも使える要求境界を定義する。

## 2. System under assessment

Gate Aでいうbodyには、Minecraft内でmissionを遂行するための次の責務を含む。

- player lifecycleとworldへの参加
- world・entity・inventory状態の観測
- 移動、経路探索、interaction
- 採取、pickup、inventory操作
- craft、加工、storage
- block配置と除去
- taskの開始、進行、終了、失敗
- transient failureからの回復
- death、restart、chunkやworld lifecycleとの整合
- 権限・安全境界の遵守
- 外部から検証可能な状態・結果・failureの提示

候補がこれらを一つのrepositoryで提供する必要はない。複数部品で構成する場合も、統合後の責任境界とfailure伝播が検証できなければならない。

## 3. Assessment mode

Gate Aはdeterministic body modeで行う。

- Jev、DeepSeek、その他の推論モデルをmission判断に使用しない
- 自然言語生成や人格表現を成功条件に含めない
- 同じ初期条件とcommandから、比較・再実行可能なmissionを開始できる
- body内部の「成功」自己申告だけでなく、inventory、world、position、structureなど結果状態から完了を確認できる
- survivalとして報告するrunでは、未申告のteleport、hidden world scan、forced pickup、直接的なworld mutationなどの特権操作に依存しない

test fixtureが初期状態を構築するために特権操作を使う場合、mission開始前の準備とmission中のbody能力を混同しない。

## 4. Capability intent

### 4.1 Lifecycle integrity

bodyはspawn、despawn、death、respawn、server stop、server restartを明示的な状態遷移として扱う。過去processのtask、lease、callback、副作用が新しいruntimeへ不正に侵入しない。

### 4.2 Observation integrity

mission判断に使う観測は、選択した運用境界で利用可能なMinecraft状態と一致する。未知、未読込、見えない、古い状態を、既知の現在状態として扱わない。

### 4.3 Locomotion and reachability

bodyは自然地形、障害、高低差、到達不能な目的地を区別して扱う。進展していない移動を成功や継続中として無期限に報告しない。

### 4.4 Interaction correctness

採取、pickup、container、craft、加工、配置、除去は、実際のworldとinventoryの変化で結果を確認する。task終了をmission成功と同一視しない。

### 4.5 Resource lifecycle

資源を見つけるだけでなく、取得、運搬、収納、取り出し、加工、消費までを連鎖したmissionとして扱える。途中のinventory圧迫、tool消耗、資源不足がsilent corruptionにならない。

### 4.6 Construction integrity

構造物の完了は、配置を試みた回数ではなく期待状態との照合で判断する。不足、置換、到達不能、壊れたblockを完成として隠さない。

### 4.7 Recovery and reconciliation

transient failureは、原因を観測でき、回復行動に上限があり、元missionへ整合的に復帰するか明示的failureで終了する。restart後は保存済み自己申告を盲信せず、worldの事実とreconcileする。

### 4.8 Safety and authority

bodyは許可されたactor、target、region、capabilityの範囲だけを変更する。未知または未許可のmutationを成功のために正当化しない。停止・pause・quarantineなどoperator controlがbodyの自律動作より優先される。

### 4.9 Inspectability

現在task、phase、進展、failure、recovery、最終結果を外部から追跡できる。silent retry loop、successへのfailure吸収、fallbackによるprimary failureの隠蔽を許さない。

## 5. Mission semantics

Gate Aの評価単位はprimitive actionの一回の成功ではなくmissionである。

```text
declared initial state
  -> mission command
  -> one or more body tasks
  -> zero or more bounded recoveries
  -> externally verifiable terminal result
```

missionは少なくとも次のいずれかで終了する。

- `COMPLETED`: 結果状態がpostconditionを満たす
- `FAILED`: 回復不能または回復予算を使い切り、理由を示して停止する
- `CANCELLED`: operatorまたはtest controllerが明示的に中止する
- `PARTIAL`: 一部だけ達成したことを成功と区別して報告する

名称は候補実装に強制しないが、意味上の区別は必要である。

## 6. Core terms

### Mission completion after bounded recovery

途中のattemptが失敗しても、有限かつ観測可能な回復の後、最終postconditionを満たすこと。許容する回復回数や時間はGA-005で定義する。

### Human intervention

通常のmission commandと事前に定義したoperator control以外に、人間がteleport、item付与、block修正、task書換え、process内状態の修復を行うこと。診断のための観測はinterventionに含めない。

### Permanent stall

postconditionへ進展せず、明示的な待機理由もterminal failureも提示しない状態が続くこと。判定窓はGA-005で定義する。

### Unauthorized mutation

missionとtest fixtureが許可していないblock、entity、inventory、container、player stateへの変更。成功後に戻した場合も、未記録ならunauthorized mutationである。

### Recovery

検出したfailure原因に対応し、同じ失敗の無制限反復ではない有限の状態遷移。replan、再取得、経路変更、reconcileなどを含み得る。

### Observable failure

原因、発生task/phase、terminalかretryableか、実施したrecoveryをEvidenceから追跡できるfailure。

## 7. Unacceptable failure classes

次は数値thresholdにかかわらずGate Aの意図に反する。

- crash、process hang、world/save corruption
- 無期限またはsilentなretry・stall
- postcondition未達を`COMPLETED`と報告
- 同一副作用の意図しない重複適用
- restart後のtask、inventory、world状態の矛盾
- 未申告のoperator能力によるsurvival成功
- unauthorized mutation
- 人間が救済しなければterminal stateへ到達しないmission
- failureやfallbackを成功ログへ吸収して原因を失うこと
- test assertionを弱めることでbody defectを隠すこと

一時的なpath failure、資源不足、満杯inventory、tool破損、deathなどは、それ自体を直ちに不合格とはしない。bounded recoveryまたは明示的terminal resultへ到達できるかを評価する。

## 8. Required scenario families

Gate A Contract v1は、少なくとも次のscenario familyを具体化する。

- lifecycleとspawn
- navigationと到達不能
- resource acquisitionと搬送
- inventory、storage、craft、加工
- deathとrecovery
- restartとreconciliation
- fixed construction
- failure injection
- unattended soakと長いtask chain
- authorizationとworld mutation boundary

具体的な件数、距離、反復回数、構造規模、実行時間は本Intentでは決めない。

## 9. Out of scope

Gate Aは次を証明しない。

- Jevがruleより良い判断をすること
- DeepSeekが自然な日本語を生成すること
- personality、relationship、memory retrievalの品質
- creative project planningやbuilding grammar
- multiplayer social behavior
- open-domain dialogue
- 数週間・数か月運用の最終的な長期安定性
- body候補の保守コストが許容可能であること。これはGA-003/004で扱う

Gate A合格はResident完成を意味しない。認知層を評価してよい最低限のbody境界を意味する。

## 10. Candidate neutrality

このIntentは`mc_aiplayer`、Mineflayer、Carpet fake player、独自実装のいずれにも適用できる。

- 上流に既存testがあることを能力証明とみなさない
- 特定のclass、command、artifact formatを要求しない
- 欠けた能力を必ずその候補へ実装するとは決めない
- 結合コストや独立検証不能性をREJECT理由として認める

## 11. Deferred to GA-005

次はGA-002/003/004のEvidenceを得た後に確定する。

- scenarioとfixtureの正確な定義
- seed、反復、距離、数量、構造規模
- timeout、stall window、recovery budget
- pass/fail thresholdと統計的扱い
- trace/event/artifact schema
- canonical runnerとexecution environment
- black-box assertionの実装境界
- soak durationと長期試験への昇格条件

これらを候補の現状へ都合よく合わせるのではなく、観測可能性とResident用途の両方から決定する。

## 12. Open questions

GA-001時点では次を未確定として保持する。

- survival境界で許可するfixture操作とmission中capabilityの厳密な分離方法
- 複数body候補へ共通化できる最小black-box control surface
- restart試験でprocess、server、worldのどの境界を分けるか
- authorized region/mutationをtest worldでどう表現するか
- long-run gateをGate A v1へ含める範囲と後続gateへ送る範囲

未確定事項はGA-005までにEvidenceに基づいて解消するか、明示的なblocked itemとして残す。
