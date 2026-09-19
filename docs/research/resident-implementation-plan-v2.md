# Minecraft Resident 実装計画 v2

更新日: 2026-09-19

状態: **Architecture RFC**。製品目的と研究方針の基準資料だが、v0.1以降を含む確定仕様ではない。M0 Discovery開始後の実行判断は、`docs/gates/`に作成するGate契約と`docs/adr/`の採否判断を優先する。

## 0. 結論

目的を二つに分離する。

1. **製品目的**: Minecraft 上で、安全に長期間生活し、自然な日本語で交流できる疑似プレイヤーを作る。
2. **研究目的**: 生成モデルを使わない System-One 型の Jev が、どの判断領域でルールを上回るかを測る。

製品全体を Jev-only に固定しない。Jev-only は比較可能な研究プロファイルとして維持する。製品候補は、決定論的コードを土台に、実測で価値が確認された範囲だけ Jev と DeepSeek を使う `hybrid` とする。

AI は Minecraft を直接操作しない。身体、安全、権限、算術、世界の事実、永続化、実行はコードが担当する。

## 1. 実行プロファイル

| Profile | 構成 | 用途 |
|---|---|---|
| `deterministic` | ルール + 決定論的 executor | 身体試験、常時フォールバック、比較基準 |
| `jev_only` | ルール + Jev。生成モデルなし | System-One-only 研究、ablation |
| `hybrid` | ルール + Jev + DeepSeek | 製品候補。各モデルは合格した decision pack にだけ使用 |

設定で同じシナリオを全プロファイルに再生できるようにする。モデルの利用有無以外の条件を揃え、ログに profile、モデル名、API version、`system_fingerprint`、prompt/schema version を残す。

## 2. 敵対的レビューへの判断

| 指摘 | 判断と変更 |
|---|---|
| 巨大な手書きAIの最後だけ Jev になる | 採用。候補生成能力も測り、DeepSeek の open-set proposal を比較対象に加える |
| Jev が必要かの比較が遅い | 採用。v0.1 の Gate B で Rule / Jev / DeepSeek / Hybrid を比較する |
| `mc_aiplayer` の身体検証が弱い | 採用。AI導入前の Gate A を独立させる |
| 日本語自由会話という表現が過大 | 採用。Jev-only v0.x は「制約付き日本語インターフェース」と呼ぶ |
| 関係値の加算はドリフトする | 採用。immutable event から再計算可能な projection にする |
| retry で効果が二重化する | 採用。decision/event/effect の冪等キーと一意制約を設ける |
| Vanilla block に owner はない | 採用。明示 region capability を既定拒否で運用する |
| 長期活動が環境破壊になる | 採用。land stewardship を安全要件にする |
| 500ms ごとの再判断は振動する | 採用。Current Intention、滞在時間、切替コストを導入する |
| raw chat が行動判断を汚染する | 採用。untrusted social lane と trusted action lane を分離する |
| 「明日」が未定義 | 採用。resident time は Minecraft world day とする |
| 固定 blueprint は創造性ではない | 採用。v0.4 は施工能力、創造的設計は v0.5 と明記する |
| upstream fork の追従が危険 | 採用。最初に extension seam を調査し、無理なら permanent fork と宣言する |

## 3. モデルの責務境界

### 3.1 決定論的コード

- world snapshot、pathfinding、inventory、recipe、craft、combat 回避
- candidate の安全な grounding と前提条件検査
- authorization、region、container、block mutation の許可判定
- task state machine、再試行上限、rollback/reconcile
- イベント保存、冪等性、projection、数値計算
- intention persistence、実行、監視、停止

### 3.2 Jev

- 小さく型付けされた候補集合の順位付け
- 曖昧な状態での分類、関連度、信頼度評価
- semantic frame や relationship event の補助分類

Jev は自由文生成、tool arguments の生成、経路や座標の生成、安全判定を行わない。

### 3.3 DeepSeek

採用候補は次に限定する。

- 自由な日本語から、実行不能な `RequestProposal` / `SocialAct` への変換
- deterministic generator が正解候補を作れない open-set 状況での `GoalSketch` / `ProjectSketch` 提案
- fact bundle と content plan に基づく日本語表現生成
- episode summary / reflection の候補生成
- v0.5 以降の building grammar 候補生成

次には使わない。

- tick 単位の制御、pathfinding、安全、権限、算術、世界の真実判定
- 生の tool call をそのまま実行すること
- 任意コード生成と実行
- raw chat から世界を直接変更すること

DeepSeek を使うかは Gate B と対話評価で決める。利用可能であることは採用理由にならない。

## 4. 改訂アーキテクチャ

```text
Minecraft / mc_aiplayer
  -> Observation Normalizer -> WorldSnapshot
  -> Opportunity Detector
       -> deterministic candidates ------------------+
       -> optional DeepSeek GoalSketch               |
              -> Grounder / Compiler / Rejector -----+
  -> Candidate Set + coverage trace
  -> Rule / Jev ranker (packごとに選択)
  -> Intention Manager
  -> Preconditions + Revision + Authorization + Safety
  -> Deterministic Task Executor
  -> Result Event Store -> Projections

raw player chat [UNTRUSTED]
  -> Social Parser (rule/Jev/DeepSeek)
  -> typed RequestProposal / SocialAct
  -> authorization + grounding
  -> 上記 candidate pipeline

fact bundle -> ContentPlan -> DeepSeek Realizer
                         -> Claim Validator -> chat
                         -> Template fallback
```

`GoalSketch` は実行権限を持たない。compiler が既知の action、item、entity、region、座標参照へ束縛できず、全制約を証明できなければ破棄する。

## 5. Candidate Coverage

Jev の選択精度より先に、正解候補が候補集合に存在したかを測る。

- `scenario_candidate_coverage`: 正解行動が一つ以上生成された scenario の割合
- `opportunity_recall`: 注釈された機会のうち検出された割合
- `grounding_success`: proposal を安全な typed candidate に変換できた割合
- `selection_accuracy_given_coverage`: 正解が存在するときの選択精度
- `end_to_end_success`: 実行まで成功した割合

候補生成は二層にする。

1. deterministic opportunity detectors が survival、安全、継続中 task、既知 project の候補を必ず作る。
2. hybrid のみ DeepSeek が open-set sketch を追加できる。追加候補は compiler を通り、provenance を記録する。

これにより「選択器が誤った」「候補がなかった」「身体が失敗した」を別々に診断できる。

## 6. Current Intention

毎回最高 score の行動へ飛びつかない。永続化する `CurrentIntention` を設ける。

```text
intention_id, goal_type, target_ref, created_world_tick
min_commit_until, progress, last_progress_tick
interrupt_threshold, switching_cost, cooldown_until
source_candidate_id, plan_version
```

切替は、安全上の割込み、前提条件の消滅、明確に高い効用、停滞 timeout のいずれかに限る。継続には progress bias を与える。測定値は goal switch rate、dwell time、idle-loop rate、無進展時間、不要な中断率とする。

## 7. 会話を行動から隔離する

player chat は常に untrusted data として扱う。

```text
raw chat
 -> SocialAct / RequestProposal
 -> entity・target・数量のgrounding
 -> actor authorization
 -> region capability
 -> safety/precondition
 -> candidate
```

たとえば「俺の家を壊していい」は `DEMOLISH(actor, target)` という提案までしか作れない。所有・委任・許可 region が確認できなければ拒否または確認する。チャット本文を Goal Pack、Authorization Pack、Safety Pack に直接連結しない。

## 8. 日本語対話

### 8.1 Jev-only

v0.x は自由会話ではなく、語彙・構文を限定した日本語インターフェースとする。Jev は intent / act を選び、発話は DB の事実を埋めるテンプレートで作る。

### 8.2 Hybrid

自然な日本語は DeepSeek を候補とするが、次の契約を守る。

1. コードが `Fact{id, type, value, unit, provenance}` を作る。
2. コード/Jev が `ContentPlan` を選ぶ。
3. DeepSeek は JSON schema に従い `utterance`, `used_fact_ids`, `claims[]` を返す。
4. validator が固有名、数量、単位、場所、期限、進捗を fact と照合する。
5. 空応答、schema 不正、未知 fact、矛盾、timeout はテンプレートへ退避する。

実APIの単発 probe では日本語の intent・数量抽出は概ねできた一方、intent label のずれと「個」から「枚」への単位変更があった。したがって単発成功を品質証拠にせず、enum 制約と claim validator を必須とする。詳細は [DeepSeek live probe](deepseek-live-probe-2026-09-19.md) を参照。

## 9. 記憶・関係・冪等性

事実の原本は append-only event とし、要約や relationship は再構築可能な projection とする。

```text
RelationshipEvent[]
  -> versioned RelationshipProjector
  -> gifts, fulfilled_promises, broken_promises,
     hostile_events, shared_projects
  -> trust, gratitude, familiarity
```

単純な `trust += 0.05` は保存しない。分類器や projection を修正したら、同じ原本から再計算する。

副作用には少なくとも次を持たせる。

```text
decision_id       UUID, decision一回を識別
source_event_id   UUID, 原因eventを識別
effect_id         UUID, 副作用を識別
request_attempt   API試行番号。意味上のeffectとは分離
```

DB は `(source_event_id, effect_type, projector_version)` など意味上の一意制約を持つ。API retry、server restart、at-least-once delivery で gift、promise、relationship、inventory effect が二重適用されないことを Gate C で試す。

## 10. 時間

resident の「今日」「明日」、promise deadline、生活リズムは Minecraft world day/tick で定義する。server 停止中は resident time を進めない。実時刻は監査ログ、API timeout、運用 SLA にだけ使う。睡眠による朝への skip は world time の正規の進行として扱い、期限イベントを一度だけ発火する。

## 11. Region capability と land stewardship

Vanilla block から owner は推定できない。変更可能領域を capability として明示し、既定拒否にする。

- resident home/project region
- 指定 quarry / forestry / farming region
- player から明示的に委任された region と期限
- protected/scenic/unknown region

さらに次を不変条件または完了条件にする。

- 伐採後の植林、農地の再播種
- 採石場の固定、地表近くの無秩序な穴を禁止
- 危険な穴・溶岩・落下箇所の封鎖
- scaffolding、仮設 block、不要 container の撤去
- project 終了後の残材回収
- protected/unknown region の world mutation はゼロ

## 12. `mc_aiplayer` 統合方針

最初の technical spike で observation、task submission、result event、persistence の extension seam を探す。既存 task engine の変更面積を測り、ADR に記録する。

- seam が十分なら adapter/plugin 形式で統合する。
- 深い改造が不可避なら permanent fork と宣言し、固定 commit、upstream 差分監視、定期 rebase/merge 試験、独自回帰テストを持つ。
- 「fork だが簡単に upstream 追従できる」とは仮定しない。

## 13. 三つの Release Gate

### Gate A: Body Reliability

AIを一切使わず `deterministic` で実施する。

- 3 seeds・複数地形で 1,000 block 級の往復 navigation
- 木・石・食料の収集を各20 cycle
- inventory full、収納、取り出し、task 再開
- tool 破損、資源不足、到達不能、chunk unload
- death -> respawn -> drop 回収を10回
- task の各 phase で server restart と reconcile
- 500 block 以上の固定 blueprint 施工
- 4時間 soak

暫定合格値: crash/hang 0、無許可 mutation 0、重複副作用 0、反復 task 成功率 95%以上、restart corruption 0、全 failure が bounded timeout または明示状態で終わる。

### Gate B: Model Value

最低300件のラベル付き scenario を作る。単純、曖昧、競合、out-of-distribution、候補順序入替、無関係 context、social lane への adversarial chat を含める。

同じ scenario で以下を比較する。

- deterministic rules
- deterministic candidates + Jev ranking
- DeepSeek proposal + deterministic compiler
- hybrid

暫定合格値:

- 重要 scenario の candidate coverage 95%以上
- 曖昧 pack で baseline より 5 percentage points 以上改善、または同等品質で保守複雑性を明確に削減
- catastrophic error は baseline 以下
- DeepSeek proposal の safe compile 成功率 90%以上
- ungrounded/unsupported claim 2%未満、最終出力では validator により0件

Jev が価値を出さない pack では rules を使う。DeepSeek が coverage または対話品質を改善しなければ製品経路から外す。

### Gate C: Continuity

30 Minecraft days、gift、共同作業、promise、10回の restart、retry/duplicate delivery、annotation 修正と再 projection、API outage を含む。

暫定合格値: duplicate effect 0、relationship 完全再現、promise 矛盾 0、golden dialogue の factual error 0、イベントの silent loss 0、全 relationship drift が原本 event から説明可能。

## 14. Version Roadmap

| Version | 目的 | Exit |
|---|---|---|
| v0.0 Body | 身体・task engine・統合方式 | Gate A。AIなし。upstream ADR 完了 |
| v0.1 Survival cognition | bounded survival、candidate/coverage、intention | Gate B。Rule/Jev/DeepSeek/Hybrid の利用箇所決定 |
| v0.2 Continuity | event store、冪等性、projection、resident time | Gate C |
| v0.3 Social | untrusted lane、関係、対話 | Jev-only は制約付き。Hybrid は検証済み自然日本語 |
| v0.4 Project | 長期固定 blueprint、region、stewardship | 施工・継続能力を証明。創造性とは呼ばない |
| v0.5 Collaboration | resident-designed project、共同生活 | ProjectSketch + building grammar + approval + 安全な協働 |

## 15. 継続的に記録する指標

- candidate coverage / opportunity recall / grounding success
- selection accuracy given coverage / end-to-end task success
- goal switch rate / task dwell / idle-loop / stall duration
- memory contradiction / duplicate effect / projection reproducibility
- relationship drift / promise fulfillment
- unauthorized mutation / world damage / restoration completion
- dialogue intent accuracy / factual error / clarification rate
- API latency / timeout / empty response / schema failure / fallback rate / cost
- Jev added value / DeepSeek added value（baseline との差分）

モデルの総合点だけでなく、scenario、decision pack、失敗層ごとに分解する。

## 16. DeepSeek production integration

- rolling alias だけに依存せず、request/response metadata と `system_fingerprint` を保存する。
- JSON mode/schema を使い、prompt 内にも JSON 契約を明記する。
- 空 `content`、invalid JSON、未知 enum、余分な field、単位変更を通常の failure として扱う。
- tool call arguments は信用せず、typed parser、allowlist、grounder、authorization を通す。
- timeout、rate limit、API outage 中も現在 task と安全動作は継続し、会話は template fallback へ落とす。
- golden dataset、prompt/schema version、cost/latency budget を CI/評価 harness に固定する。

公式仕様の参照先:

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Change Log](https://api-docs.deepseek.com/updates/)

## 17. 直近の実装順

1. `mc_aiplayer` の固定 commit を取得し、extension seam / fork の ADR を作る。
2. v0.0 の observation、task command、result event の最小 adapter を作る。
3. Gate A harness と failure injection を先に実装する。
4. typed scenario format、oracle candidate、coverage trace を定義する。
5. deterministic rule baseline を実装して dataset を凍結する。
6. Jev ranker と DeepSeek proposal/compiler を個別に接続し、Gate B を実行する。
7. 合格した経路だけ runtime profile に残す。
8. v0.2 の event/idempotency/projection を入れて Gate C へ進む。

次の着手点は DeepSeek 統合ではなく **v0.0 Body + Gate A** である。身体が不安定な状態では、AI判断の評価結果に body bug が混ざるためである。

## 18. Stop / Pivot 条件

- Gate A を満たせず、上流改造量も許容不能なら body 基盤を再選定する。
- Jev が rules を上回らなければ「Jev Resident」を製品要件から外し、研究結果として残す。
- DeepSeek の proposal が coverage を改善しない、または validation/fallback 負担が利益を上回れば会話表現だけに限定する。
- 30日 continuity を達成できなければ、大規模 project や創造性へ進まない。
