# Jev-only Minecraft 疑似プレイヤー 調査・実現計画

> **Status:** Jev-only feasibility study として保存する。敵対的レビューと DeepSeek 利用可能性を反映した今後の authoritative plan は [Minecraft Resident 実装計画 v2](resident-implementation-plan-v2.md)。本書の一次調査・Jev能力境界・OSS調査は引き続き参照資料として有効である。

調査日: 2026-09-19 (Asia/Tokyo)

対象: Minecraft Java Edition 上で、生成LLM・埋め込みモデルを使わず、AIモデルは TypeSafe AI の Jev だけを使う永続的な疑似プレイヤー

結論の有効期限: Jev は公開直後の early access であるため、モデル/API/価格に関する記述は実装開始時と各リリース前に再確認する。

## 0. 結論

実現可能。ただし完成物は「JevがMinecraftを直接プレイするbot」ではない。

実現可能な形は次の分業になる。

1. Minecraft/Fabric側の決定論的コードが、身体、視界、移動、採掘、クラフト、戦闘回避、建築、永続化を受け持つ。
2. コードが、その時点で実行可能な具体的候補を列挙する。
3. Jevは候補の選択、曖昧な発話の分類、記憶価値、関係変化、対話行為など、狭く型付けされた判断だけを行う。
4. 自由文の生成は行わず、`DialogueAct -> ContentPlan -> ClausePlan -> TemplateRealizer` で発話する。
5. 算術、安全制御、権限、行動前提条件、完了判定はJevに任せない。

推奨する実装基盤は、**Fabric 1.21.3 の [`mc_aiplayer`](https://github.com/zoyluoblue/mc_aiplayer) をMITライセンスの上流として固定し、そのLLM BrainをJevの候補選択器へ置き換える方式**である。調査時にソースを確認したコミットは `a029fa6a3760fd0f83834c104051b041d986da60`。

Mineflayerは最速の実験基盤として優秀だが、本目的では次の理由から第二候補とする。

- オンラインモードの通常サーバーではMicrosoft認証を行う実アカウントが必要になる。
- botプロセスとサーバーが分離し、再起動、認証、ネットワーク切断を別途扱う必要がある。
- 「サーバー内に一人の永続住民を置く」という目標には、サーバー側 `ServerPlayerEntity` の方が自然である。

一方、完全に自由な日本語会話や、未知の概念を含む文章の生成は、strict Jev-onlyでは達成不能である。これは実装不足ではなく、Jevが文字列生成を提供しないという能力境界である。会話品質を合格条件にするなら、初期版では「制約付き会話」と明記する必要がある。

## 1. 「Jev-only」の作業定義

この計画では次の定義を採用する。

- 使用する学習済みAIモデルはJevのみ。
- 生成LLM、視覚言語モデル、音声モデル、埋め込みモデルは使わない。
- Javaの通常コード、有限状態機械、A*、レシピ表、ルール、SQL、全文/タグ検索、形態素解析器、テンプレートは利用可能。
- Minecraftの正規API/データと、ライセンス上再利用可能なOSSを利用可能。
- Jev APIが停止しても安全確保と現在タスクの停止/継続判断が壊れない。

この定義で「Jevだけ」は「全処理をJevで行う」という意味ではない。Jevは判断器であり、身体制御器、データベース、探索器、自然言語生成器ではない。

## 2. Jevの確認済み能力

### 2.1 公式仕様

TypeSafeの[公式Introduction](https://docs.typesafe.ai/introduction)と[Quick Start](https://docs.typesafe.ai/introduction/quickstart)によると、APIは `state` と複数の型付き `questions` を受け取り、次を返す。

| Primitive | 用途 | 主な返り値 |
|---|---|---|
| Choice | 定義済み候補から1つ選ぶ | choice、全候補の確率、confidence |
| Score | 順序付き基準上で評価する | score、各段階の確率、confidence |
| Noul | 命題が真である確率を出す | 0..1 の確率 |

同一request内の質問は同じstateを見ながら独立・並列に評価される。質問間の依存はない。後続判断が先行回答を必要とする場合だけ、コードで二段目のrequestを作る。

重要な仕様:

- Choiceは最大255候補。網羅できない場合は `other` / `none` を明示する（[Choice docs](https://docs.typesafe.ai/primitives/choice)）。
- 複数の判断を一質問に詰めず、一質問一判断に分解する（[Primitives docs](https://docs.typesafe.ai/primitives)）。
- confidenceは正答確率ではなく、候補分布の尖り方から得る指標。用途ごとに自前データで閾値を較正する（[Confidence docs](https://docs.typesafe.ai/confidence)）。
- `jev-latest` は中身が変わる。較正後はversioned modelを固定する。
- 2026-09-19の疎通では `jev-latest` は `jev-1.13.0` に解決された。
- 価格は調査時点で入力 `$0.042 / 1M tokens`、出力は無料と公式発表されている。ただしearly accessのため固定前提にしない（[公式発表](https://typesafe.ai/blog/introducing-system-one-models-and-jev)）。

### 2.2 何をさせるべきか

Jevに適する処理:

- 実行可能なGoal/Task候補の選択
- プレイヤー発話の限定されたintent / dialogue act判定
- 同一発話に複数intentが含まれるかの独立Noul判定
- eventの重要度、記憶候補の種別、関係への影響
- 既知候補から注目対象を選ぶ
- 曖昧さを検出し、質問・保留・安全な既定動作へ分岐する
- personality/valueに照らした候補選択
- 候補テンプレートから発話表現を選ぶ

Jevにさせない処理:

- 座標、個数、レシピ、所要量、時刻の計算
- 20 TPSの移動や危険回避
- 世界に存在しないitem/place/actionの発明
- 任意のtool argument生成
- 自由文生成
- 長い計画の一括作成
- 破壊、攻撃、所有権変更などの権限判定を単独で確定すること

### 2.3 公式/実装資料が示す弱点

[Pydantic AIのTypeSafe統合資料](https://pydantic.dev/docs/ai/models/typesafe/)は、Jevについて次を明記している。

- 算術、数え上げ、日付に弱い。
- 一質問に複数判断を入れると弱い。
- 多段の間接推論で精度が落ちる。
- 無関係なcontextが増えるほど精度が落ちる。
- adversarial text / prompt injectionの影響を受ける。
- Choiceの候補順を変えると回答が動くことがある。
- text、tool arguments、画像、音声、動画、文書を生成/読取できない。
- validatorで同じ質問を再試行しても、回答をLLMのように自己修正しない。

従って、公式サイトの「can't hallucinate」「zero hallucinations」は、**型外の文字列を生成しない**という狭い意味で読むべきである。定義済み候補の中から意味的に誤った候補を高信頼で選ぶことはあり得る。

### 2.4 Context上限の扱い

公式Primitives資料はstateとquestionsの共有予算を「およそ32,000 tokens」としている。一方、Pydantic統合資料は `jev-1.13` について total 64k、state + longest question 32k と記載する。記述に差があるため、設計上は次を採用する。

- 1 requestを8k tokens未満に抑える。
- World全体や全履歴を渡さず、decision packごとに必要なfactsだけを構築する。
- 上限はSDK/APIの契約testで検出し、ドキュメント値をハードコードしない。

## 3. このリポジトリでのライブprobe

詳細な再現入力とresponseは [`jev-live-probes-2026-09-19.md`](./jev-live-probes-2026-09-19.md) に保存した。これは性能benchmarkではなく、API疎通と設計仮説を確かめる少数のfunctional smoke probeである。

要点:

1. `tools/probes/jev_client.py` の英語survival stateでは `gather_wood` を confidence 0.97で選択した。
2. 英語の「時計塔の進捗質問 + 明日ガラスを持参する約束」は、進捗質問0.99、約束0.97、記憶種別 `commitment` confidence 0.92、返答行為 `report_and_thank` confidence 1.0だった。
3. 同義の日本語発話を英語質問で判定すると、進捗質問0.18、約束0.08、意味 `unclear` confidence 0.93だった。
4. 同義の日本語state + 日本語questionsでも主要判定に失敗した。
5. `danger=false` でも「安全行動よりprojectを優先してよいか」は0.56に留まった。安全は曖昧な言語判断にせずコードで処理すべきという根拠になる。

結論: **現行 `jev-1.13.0` に生の日本語自由文理解を依存してはいけない。** 公式資料に日本語対応保証も見つからなかった。

## 4. Minecraft上の「疑似プレイヤー」方式比較

| 方式 | 身体 | 長所 | 短所 | 本件評価 |
|---|---|---|---|---|
| 外部protocol client | Mineflayer等が通常playerとして接続 | 成熟API、version幅、豊富なplugin、開発が速い | online-mode認証/アカウント、別process、切断、server外状態 | PoC向き、製品第二候補 |
| server-side fake player | Fabric mod内でServerPlayerEntityを生成 | bot account不要、server/world lifecycleと統合、永続住民に合う | Minecraft内部API依存、version更新負荷、技能を自作/移植 | **推奨** |
| NPC entity/plugin | Citizensや独自LivingEntity | 表示/対話/NPC管理が容易 | player固有mechanicsと完全互換でない | 会話NPCなら可、疑似playerには不十分 |
| Carpet fake player | `/player`でfake playerを生成/操作 | 実績、技術系serverで定番、軽い | 主にcommand駆動、生活AI/技能/長期記憶は別実装 | body spike/比較対象 |
| client mod + Baritone | 実client内部のpathfinder | 長距離path、採掘/設置考慮、chunk cache | client/accountが必要、server residentと運用形態が違う | navigation参考、直接基盤は非推奨 |

### Mineflayer

[`PrismarineJS/mineflayer`](https://github.com/PrismarineJS/mineflayer) はJava Edition bot用の成熟したMIT OSS。block/entity、physics、inventory、craft、dig/build、chatを提供し、pathfinder、state machine、PvE、auto-eat、collectblock等のpluginがある。調査時はMinecraft 1.8から26.1までをREADMEが掲げていた。

認証はMicrosoftまたはoffline mode。公式READMEは `auth: 'offline'` をoffline-mode server向けとしている。公開/通常online-mode serverに置く場合、bot用Microsoft/Minecraftアカウント運用が必要になる。

適用判断:

- 1週間以内にJevのdecision loopを目で確認したい場合は最速。
- 最終要件が「server内の住民」「追加アカウント不要」「server再起動と一体」なら、後でserver modへ移植する二重投資になる。

### Fabric Carpet

[`gnembon/fabric-carpet`](https://github.com/gnembon/fabric-carpet) はMIT。fake playerをspawnし、移動/attack/use等をcommandで制御できる。fake playerの技術的先例として重要。ただし生活AI、資源獲得FSM、意味記憶、会話は提供しないため、本件の大部分は別実装になる。

### Paper FakePlayer / Citizens

- [`tanyaofei/minecraft-fakeplayer`](https://github.com/tanyaofei/minecraft-fakeplayer) はPaper/Purpur用Apache-2.0。spawn、inventory、attack、mine、use、jump等の操作を提供するが、README上の最終pushは2025-11で、生活AI基盤ではない。
- [`Citizens2`](https://github.com/CitizensDev/Citizens2) は長寿命のBukkit/Paper NPC API。NPC演出には強いが、「本物のplayer mechanicsを持つsurvival resident」とは目的が異なる。ライセンスはOSL-3.0で、組込み前に配布形態を確認する。

### Baritone

[`cabaletta/baritone`](https://github.com/cabaletta/baritone) はLGPL-3.0のclient側pathfinder。A*、長距離segment、chunk cache、block破壊/設置、危険block回避等が成熟している。設計/アルゴリズムの先行例として有用だが、server-side `ServerPlayerEntity` へそのまま接続できる部品ではない。

## 5. 先行AI agent OSS調査

2026-09-19時点のGitHub APIで活動・licenseも確認した。starは成熟度の補助指標に過ぎず、能力保証ではない。

| OSS | 主用途/構成 | 再利用価値 | 本件での限界 |
|---|---|---|---|
| [`mc_aiplayer`](https://github.com/zoyluoblue/mc_aiplayer) | Fabric server-side player、Goal/Task FSM、A*、snapshot | **body/skill/persistenceの第一候補** | BrainがOpenAI tool call前提。memory/social/NLGは不足 |
| [`Mineflayer`](https://github.com/PrismarineJS/mineflayer) + plugins | 外部client bot platform | PoC、API/skill実装、比較oracle | account/process運用 |
| [`Voyager`](https://github.com/MineDojo/Voyager) | Mineflayer + GPT-4、自動curriculum、code skill library | skill library、feedback、評価思想 | 2024以降更新薄い。program synthesisがJev不可 |
| [`mindcraft`](https://github.com/mindcraft-bots/mindcraft) | Mineflayer + LLM + 多数の高位action | action taxonomy、multi-agent、chat hook | LLM/tool generation/要約/RAG前提 |
| [`ai-companion`](https://github.com/adevivo/ai-companion) | Fabric LivingEntity + AltoClef + Automatone/Baritone fork | navigation/task engine分離の参考 | MC 1.20.1、LGPL、LLM text/command/embedding前提 |
| [`CraftAgent`](https://github.com/prskid1000/CraftAgent) | Fabric NPC、SQLite conversation/private/shared memory | context/memory schemaの参考 | LLM JSON action + text前提、実績小 |
| [`CraftAssist`](https://github.com/facebookresearch/craftassist) | dialogue-enabled Minecraft assistant | dialogue/memory研究の歴史的参考 | archived、player resident目的と違う |
| [`GITM`](https://github.com/OpenGVLab/GITM) | text knowledge + memoryでtech tree攻略 | planning/memory研究 | repoにlicense表記がなく、直接再利用不可 |

### 5.1 `mc_aiplayer` ソース確認結果

調査した固定commitには次が実在する。

- `AIPlayerEntity extends ServerPlayerEntity`
- 9種類のsealed `Goal`
- Goalを依存stepへ展開する `GoalPlanner`
- 34種のdeterministic Task state machine（README自己申告とソースを照合）
- `ActionPack`、A* pathfinder、perception snapshot
- versioned runtime snapshotとatomic persistence
- strict survival/operator profile
- safety、pause/resume、authorization、restart restoration
- JUnit/GameTest/harness

一方、現在のBrainは63 toolの名前と引数をLLMに生成させる。Jevはtool argumentsを生成できないため、`BrainCoordinator` / `ToolRegistry` を単純にJev HTTPへ差し替えるだけでは動かない。

必要な変換は以下。

```text
現状:
  free-form request -> LLM generates tool name + JSON args -> ToolRegistry -> Goal/Task

Jev-only:
  event/world state
    -> deterministic candidate generator creates fully-bound CandidateAction[]
    -> Jev Choice selects candidate_id
    -> confidence/risk gate
    -> precondition + world revision check
    -> existing Goal/Task executor
```

例:

```json
{
  "candidate_id": "gather_oak_near_12_64_-7",
  "kind": "GATHER",
  "item": "minecraft:oak_log",
  "count": 8,
  "target_region": [12, 64, -7],
  "estimated_risk": "LOW",
  "preconditions": ["visible_tree", "path_exists", "axe_or_hand"]
}
```

Jevが返すのは `candidate_id` だけで、座標、item id、countを作らせない。

### 5.2 既存memoryの不足

`mc_aiplayer` の `BotMemory` は現状、文字列fact map、named places、文字列goal stepsが中心。今回必要なepisode、source付きbelief、player relationship、commitment、project contributionには足りない。body/skill基盤としては使えるが、resident memoryは新設する。

### 5.3 Jevを無理にtext generator化するOSS

[`afanjul/jev-llm`](https://github.com/afanjul/jev-llm) は、最大255の語候補から次語をChoiceで選ぶ処理を逐次繰り返し、Jevだけで文字列を作る実験。Jevの限界を確認する先行例として有用だが、本番会話には採用しない。

理由:

- 次語ごとに逐次API callが必要で、Jevの「一request内並列」の長所を失う。
- 標準word modeは英語の閉じた語彙、char modeも英小文字中心。
- 20語でも少なくとも20回、語bucketを使えばそれ以上のremote callsになり得る。
- projectは調査時2 commits、0 starsで、品質/運用実績がない。
- Minecraftのfactsにgroundされた発話保証が弱い。

短い発話なら、意味構造をコードで作って一度でsurface realizationする方が速く、正確で、test可能である。

## 6. 推奨アーキテクチャ

```text
Minecraft server / Fabric 1.21.3
│
├─ AIPlayerEntity (mc_aiplayer由来のServerPlayerEntity body)
├─ Perception + Fact Extractor
├─ ImmediateSafetyController             20 TPS、Jevを待たない
├─ Candidate Generator                   完全に引数が埋まった候補だけ作る
├─ Resident Scheduler / Event Bus
│    └─ Decision Pack Router
│         ├─ Homeostasis pack
│         ├─ Goal pack
│         ├─ Task recovery pack
│         ├─ Social pack
│         ├─ Memory pack
│         └─ Reflection pack
├─ JevClient (Java 21 HttpClient、async、version pin、circuit breaker)
├─ Confidence/Risk Gate
├─ Goal/Task FSM + A* + Actions           mc_aiplayerを再利用
├─ ResidentMemory (SQLite + append-only events)
├─ Dialogue
│    ├─ deterministic Japanese normalizer
│    ├─ DialogueAct decision (Jev)
│    ├─ Content/Clause planner (code)
│    └─ template/grammar realizer
└─ Trace / Replay / Golden Scenario eval
```

### 6.1 時間スケール

| 周期/trigger | 所有者 | 内容 |
|---|---|---|
| 毎tick (50ms) | code | collision、移動、block操作、task FSM |
| 毎tick〜100ms | code | lava、fall、oxygen、critical HP、creeper等の反射安全 |
| 500ms〜2sまたは重要event | Jev | idle時の次Goal、task失敗回復、注目対象 |
| player chat | parser + Jev | intent、対話行為、記憶候補 |
| task/goal完了 | Jev必要時のみ | 次の候補、episode significance |
| Minecraft日終端 | code + Jev 1 call | bounded reflection、翌日のpriority |

Jev latencyが何msでも、tick処理をblockしてはいけない。API呼出はserver thread外、response適用はepoch/revision一致時だけserver threadへ戻す。

### 6.2 Stale decision防止

各decision requestへ以下を入れる。

```text
resident_id
decision_pack
world_revision
task_revision
candidate_set_hash
requested_at
```

response適用前にrevision、候補存在、precondition、権限を再確認する。不一致なら `STALE_DECISION` として捨て、必要なら再判断する。

### 6.3 Safety / 権限

hard ruleで禁止するもの:

- 他player所有block/containersの破壊・持出し
- playerへの攻撃（v0.1はPvPなし）
- allowlist外dimension移動
- protected region内の建築変更
- 未許可のfire/TNT/lava使用
- confidence不足時の不可逆action

Jevのconfidenceはhard authorizationを解除できない。

### 6.4 API障害時

- 実行中の安全なTaskは短いcheckpointまで継続して停止。
- ImmediateSafetyControllerは常時稼働。
- 新Goalは開始しない。
- exponential backoff + jitter、timeout、circuit breaker。
- 最終的に `COGNITION_UNAVAILABLE` でhome/holdへ移る。
- request/responseへ秘密、全chat履歴、不要なplayer dataを入れない。

## 7. Memory設計

SQLiteをresident cognitionのsource of truthとし、Minecraft player inventory/health/positionはworld側をsource of truthとする。両者を混同しない。

推奨table:

```text
residents
events                  append-only normalized world/social events
episodes                event群のresident視点まとめ
beliefs                 subject/predicate/object/confidence/source/status
people
relationships           familiarity/trust/gratitude/caution/reliability
relationship_events
commitments             promisor/promisee/content/due/status/evidence
places
place_aliases
projects
project_phases
project_materials
project_contributors
goals
tasks
task_attempts
important_items
habits
jev_calls
jev_answers
decision_outcomes       後でaccuracy/calibrationを測るための結果
```

原則:

- 生eventを先に保存し、Jev判断で上書きしない。
- beliefには必ずsource、observed/hearsay、confidence、valid_from/toを持つ。
- relationship scoreはJevが直接自由更新せず、Jevのtyped event分類をコードの小さなdeltaへ写す。
- commitmentはpromise/fulfilled/broken/expired/unknownの状態機械にする。
- 数量、座標、project progressはcodeが計算する。
- entity key、actor、place、project、event type、time、importanceによる索引でretrievalする。
- embeddingは使わない。v0.1はexact key + tag + recency + importance + graph adjacencyで十分。

### 記憶取込みflow

```text
World/chat event
 -> deterministic normalization
 -> immutable Event保存
 -> Jev Memory Pack
      should_remember? (Noul)
      episode_type (Choice)
      social_effect (Choice)
      importance (Score)
 -> confidence/risk gate
 -> typed Episode/Belief/RelationshipEvent/Commitmentへreduce
```

未知の名前・場所aliasは、元text spanをコードで保持し、Jevに新しいstringを生成させない。曖昧ならunresolved aliasとして後でplayerへ確認する。

## 8. 対話設計

### 8.1 到達可能な会話

v0.1で扱うdialogue actsの例:

```text
GREET
ACKNOWLEDGE
THANK
REPORT_STATUS
REPORT_ACTIVITY
ASK_CLARIFICATION
ASK_HELP
ACCEPT_OFFER
DECLINE_OFFER
REMIND_COMMITMENT
WARN_DANGER
SAY_CANNOT
NO_INTERACTION
```

Jevはact、topic、含めるfacts、tone、verbosity、template familyを選ぶ。コードがDB/worldからfactsを取り、grammarが文章化する。

例:

```text
DialogueAct: REPORT_PROJECT_STATUS
ContentPlan:
  project=時計塔
  progress_bucket=4割くらい
  recent_helper=Kai
  missing_item=ガラス
  missing_count=18
TemplateFamily: FRIENDLY_MEDIUM

出力:
  時計塔は4割くらいまでできたよ。Kaiがガラスを持ってきてくれたから、
  窓もかなり進んだ。あと18枚くらいあれば足りそう。
```

factsはすべてcode/DB由来で、Jevは数値を書かない。

### 8.2 日本語入力

現行Jevへ生の日本語を渡す案はlive probeで棄却した。段階的に次を採る。

v0.1:

- `Mira、ついてきて`
- `Mira、木を16個集めて`
- `Mira、時計塔はどう？`
- `Mira、これは家だよ`
- `Mira、明日ガラスを持ってくる`

のような限定grammarをregex/辞書/必要なら非生成の形態素解析でsemantic frameへ変換する。item/player/project/placeはworld registryとalias tableへgroundする。

v0.2:

- 複数intentのNoul fan-out
- 省略/照応の限定解決
- 低confidence時のtemplate質問
- paraphrase辞書拡充

「任意の日本語雑談」は非目標として明示する。

### 8.3 Jev-only text generation hackを使わない理由

前述の`jev-llm`方式は研究デモとしては成立するが、逐次call、語彙制約、日本語非対応、groundingの弱さから採用しない。もし将来試す場合も、chat本線ではなく隔離した実験feature flagにする。

## 9. 添付会話の批判的評価

添付の主張は方向性としてかなり良い。しかし、そのまま仕様にはできない。

### 妥当

- Jevを身体制御ではなくtyped decisionへ限定する。
- safety controllerをJevから分離する。
- memoryをevent/episode/belief/relationship/projectへ構造化する。
- context builderで必要なfactsだけ渡す。
- conversationを意味決定とsurface realizationに分ける。
- project/buildingをgrammar/blueprint/BOM/taskへ分解する。
- restart、task FSM、failure reason、world revisionを一級概念にする。
- SQLiteを構造記憶へ使い、Obsidian/Markdownはprojectionに留める。

### 修正が必要

- 「Jevはhallucinateしない」: 型外生成をしないだけ。候補選択の誤りはある。
- 「日本語発話をそのまま理解」: 現行実測で失敗。保証資料もない。
- 「Jevが会話から未知の事実を抽出」: 新string生成がないため、span抽出/alias付与はコード側が必要。
- 「Jevがtoolを呼ぶ」: tool nameの選択は可能でも引数生成は不可。完全にboundされた候補を選ばせる。
- 「有限ontologyだから十分」: vanillaでも状態空間は大きく、mod追加で拡張される。registry由来の動的候補生成が必要。
- 「全decisionを数百msで」: latencyはネットワーク/地域/負荷依存。server tickから分離する。
- v0.1のscopeが大きすぎる: landmark自律建築、社会、約束、長期人格まで一度に入れるとbody reliabilityを検証できない。
- 先にFake ServerPlayerをゼロから作る案: `mc_aiplayer`に近い実装がすでに存在するため、再利用性を先にspikeすべき。

## 10. 実装ロードマップ

期間は1人開発の粗い目安。日数よりexit criteriaを優先する。

### Phase 0: 基盤spike（3〜5日）

作業:

- `mc_aiplayer` の固定commitをfork/subtreeで取り込む方法を決める。
- Fabric 1.21.3 + Java 21でbuild、server起動、fake player spawn。
- strict_survivalで木を採る、craft、食事、移動、death/restartを実行。
- Java 21 `HttpClient` からJev APIをasync call。
- model id、latency、usage、candidate hashをtraceへ保存。
- LLM Brainを無効化してもmanual typed Goalが完走することを確認。

Exit:

- bot accountなしでspawn。
- 既存deterministic taskが最低3種成功。
- server threadをblockせずJev responseを受ける。
- restart後にbody/task stateが壊れない。

Go/No-Go:

- `mc_aiplayer`のbody/taskが対象worldで不安定なら、Mineflayer PoCへ切替。
- Minecraft versionを1.21.3以外に固定する必要があるなら、port costを見積り直す。

### Phase 1: Jev decision loop（1〜2週）

作業:

- `CandidateAction`、`DecisionPack`、`DecisionResult`を導入。
- Homeostasis/Goal/Recoveryの3 packだけ実装。
- candidate生成は実行可能性をcodeで検証。
- confidence gate、other/hold候補、option-order perturbation test。
- world revision/precondition再検証。
- ImmediateSafetyControllerを完全にJev外へ置く。

Exit:

- 新worldでwood/tool/food/shelterのbounded loopを3 seedで完走。
- API失敗時に停止/帰宅し、破壊的暴走をしない。
- stale responseがworldへ適用されない。

### Phase 2: Resident memory（1〜2週）

作業:

- SQLite migrationとappend-only events。
- episode/belief/place/relationship/commitment schema。
- actor/place/project index retrieval。
- Memory Packとdeterministic reducer。
- restart/replay test。

Exit:

- gift、共同作業、約束、約束履行、death、place発見を正しく保存。
- 7 Minecraft日後/restart後に同一player/eventを参照可能。
- DBからworld stateを捏造せず、reconciliationできる。

### Phase 3: 制約付き日本語対話（1〜2週）

作業:

- 呼び掛け、request、status、offer、promise、place teachingの限定grammar。
- multi-intent fan-out。
- DialogueAct/ContentPlan/ClausePlan/TemplateRealizer。
- personalityによるverbosity/template差。
- unknown/low-confidence clarification。

Exit:

- golden utterancesのintent/slot accuracy 95%以上。
- factsと矛盾する数量/人物/出来事を発話しない。
- 未知発話に作り話で答えず、聞き返す。

### Phase 4: Project/共同建築（2〜4週）

作業:

- 固定blueprint 1種から開始。
- BOM、acquisition graph、phase、contributor、project conflict。
- player contribution検出。
- protected ownership。

Exit:

- survival資源だけで小屋または時計塔の限定blueprintを完成。
- restart後継続。
- player変更を勝手に破壊しない。

### Phase 5: Hardening / 長期運転

作業:

- 100日simulation/replay。
- API outage、429/5xx、server restart、chunk unload、death、inventory full、path impossible。
- metrics、trace replay、schema migration、backup。
- model version upgrade eval。

Exit:

- 24h soakでserver crashなし。
- destructive policy violation 0。
- decision errorからbounded timeでhold/homeへ収束。

## 11. v0.1合格条件

scope:

- 1 resident、private Fabric server、Minecraft 1.21.3。
- PvPなし。
- vanilla item/block中心。
- 日本語は限定grammar。
- landmarkは固定blueprint 1種。
- AI modelはJevのみ。

必須scenario:

1. 新worldでspawnし、木材、basic tool、食料、拠点を得る。
2. 夜/敵/lava/溺水/低HPでJevを待たず安全行動する。
3. playerから資材を受け取り、人物・project contributionを記憶する。
4. playerの将来約束をcommitmentにし、履行時にstatus/relationshipを更新する。
5. 「最近何してた？」へ実eventだけで短く答える。
6. 曖昧なproject発話へ聞き返す。
7. 固定blueprintをsurvival資源で完了する。
8. 他player所有blockを破壊しない。
9. death後にdrop回収または安全に断念し、episodeを残す。
10. server restart後もidentity、memory、project、task checkpointが続く。
11. Jev timeout/5xx時に安全にhold/homeへ移る。
12. 古いdecision responseを適用しない。

## 12. 評価方法

Jevの一般的なconfidenceを信用するだけでは不十分。Minecraft用labelled datasetを自作する。

### Dataset

- world/perception snapshots
- candidate sets
- expected safe/valid selections
- English/Japanese player utterances
- memory/no-memory labels
- relationship effects
- dialogue acts
- adversarial chat
- choice option order permutations

### Metrics

- Goal/Task success rate
- catastrophic action count
- stale decision rejection rate
- path/task recovery rate
- intent/slot precision/recall
- commitment state accuracy
- memory retrieval precision@k
- dialogue factual consistency
- confidence bin別accuracy
- low-confidence abstention/clarification rate
- Jev request count、token、latency分布、API failure rate
- server MSPT/TPSへの影響

### Release gate

- `jev-latest` はtest専用。
- production/repro runはversion pin。
- upgrade時にgolden replay、threshold再較正、option-order testを通す。
- deterministic baseline（Jevなしrule policy）と比較し、Jev追加が改善するpackだけproductionへ入れる。

## 13. Privacy / 運用上の注意

Jevはremote APIであり、送信stateはTypeSafeへ渡る。[Privacy Policy](https://typesafe.ai/legal/privacy-policy)はInputをmodel training/fine-tuningへ使わないとしている一方、service提供等に必要な期間の保持、米国での処理、service providerへの開示可能性を記載している。

従って:

- player chatを外部送信することをserver参加者へ明示する。
- UUID、IP、座標履歴、全chat logを不必要に送らない。
- decisionに必要な短いfactsだけ送る。
- API keyは環境変数/secret storeへ置き、`.env`をcommitしない。
- request/response traceは秘密除去とretention policyを持つ。
- 子供を含むserverでの運用はprivacy policyと地域法を別途確認する。
- 商用/公開配布前にTypeSafeの契約、usage limit、benchmark公開制限を確認する。

## 14. 即時の次アクション

1. 目標runtimeを **Fabric 1.21.3 / Java 21 / private server / 1 resident** と仮固定する。
2. `mc_aiplayer`固定commitの再利用spikeを行う。
3. Pythonの現clientはJev probe/eval harnessとして残し、本体用Java async clientを作る。
4. `CandidateAction` schemaとHomeostasis decision packだけを先に作る。
5. 日本語会話を後回しにし、body/task reliabilityを先に証明する。
6. Phase 0のGo/No-Go後にのみmemory schemaへ進む。

## 15. 調査ソース台帳

### Jev / TypeSafe 一次資料

- [TypeSafe AI: Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [TypeSafe Docs: Introduction](https://docs.typesafe.ai/introduction)
- [TypeSafe Docs: Quick Start](https://docs.typesafe.ai/introduction/quickstart)
- [TypeSafe Docs: Primitives](https://docs.typesafe.ai/primitives)
- [TypeSafe Docs: Choice](https://docs.typesafe.ai/primitives/choice)
- [TypeSafe Docs: Confidence](https://docs.typesafe.ai/confidence)
- [TypeSafe official Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [Pydantic AI TypeSafe/Jev integration](https://pydantic.dev/docs/ai/models/typesafe/)
- [TypeSafe Privacy Policy](https://typesafe.ai/legal/privacy-policy)
- [TypeSafe Master Customer Agreement](https://typesafe.ai/legal/mca)

### Minecraft body / navigation / NPC OSS

- [mc_aiplayer](https://github.com/zoyluoblue/mc_aiplayer) — inspected commit `a029fa6a3760fd0f83834c104051b041d986da60`
- [Mineflayer](https://github.com/PrismarineJS/mineflayer)
- [mineflayer-pathfinder](https://github.com/PrismarineJS/mineflayer-pathfinder)
- [Baritone](https://github.com/cabaletta/baritone)
- [Fabric Carpet](https://github.com/gnembon/fabric-carpet)
- [Paper FakePlayer](https://github.com/tanyaofei/minecraft-fakeplayer)
- [Citizens2](https://github.com/CitizensDev/Citizens2)

### AI agent / memory / dialogue先行例

- [Voyager](https://github.com/MineDojo/Voyager)
- [Voyager paper](https://arxiv.org/abs/2305.16291)
- [mindcraft](https://github.com/mindcraft-bots/mindcraft)
- [GITM](https://github.com/OpenGVLab/GITM)
- [CraftAssist](https://github.com/facebookresearch/craftassist)
- [CraftAgent](https://github.com/prskid1000/CraftAgent)
- [AI Companion](https://github.com/adevivo/ai-companion)
- [jev-llm](https://github.com/afanjul/jev-llm)

### ローカル根拠

- `README.md`
- `tools/probes/jev_client.py`
- 添付会話 `pasted-text.txt`（UTF-8。PowerShell既定読取では文字化けするため `Get-Content -Encoding UTF8` が必要）
- live API probes: [`jev-live-probes-2026-09-19.md`](./jev-live-probes-2026-09-19.md)

## 16. 再調査が必要になる条件

次のいずれかが起きた場合だけ、該当部分を再調査する。

- Jev modelが `1.13.x` から更新される。
- TypeSafeがtext generation、tool arguments、multilingual保証を追加する。
- Minecraft/Fabric target versionを1.21.3から変える。
- `mc_aiplayer`のlicense、architecture、maintenance状態が変わる。
- public online-mode serverへ配備する。
- 任意日本語会話が必須要件になる。
- 商用運用、個人情報、未成年playerを含む運用になる。
