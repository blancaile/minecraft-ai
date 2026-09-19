# Jev Control：ビルドと実機検証

対象は **Minecraft Java Edition 1.21.3 / Fabric Loader 0.18.4以上 / Java 21** の専用サーバー。
Paper・Spigot・Vanillaのpluginディレクトリへ入れる形式ではない。クライアントへのMOD導入は不要。

このブランチは1体の疑似プレイヤー `JevBot` を、実際の観測とJevの短い操作選択で動かすPoC。
Carpet 1.4.158とFabric API 0.114.1+1.21.3はビルド時にJARへ同梱する。
Jev APIを呼ぶPythonプロセスやNodeプロセスは必要ない。

## 1. ブランチを取得してビルド

Java 21のJDKをインストールし、`java -version` と `JAVA_HOME` が同じJDKを指すことを確認する。
Gradle本体はWrapperが取得するので別途インストールしなくてよい。

Windows PowerShell:

```powershell
git fetch origin
git switch feat/jev-embodied-control
git pull --ff-only
.\gradlew.bat clean build
```

macOS / Linux:

```sh
git fetch origin
git switch feat/jev-embodied-control
git pull --ff-only
./gradlew clean build
```

配置する成果物は `build/libs/jev-control-0.1.0.jar`。
ビルドには依存ダウンロード用インターネット接続が必要だが、`.env`・Jev APIキーは不要。
unit testはローカルHTTP stubを使い、実Jevへ接続しない。

## 2. JARを配置

1. 対象のFabric 1.21.3専用サーバーを停止する。
2. `build/libs/jev-control-0.1.0.jar` をサーバーの `mods/` に配置する。
3. サーバーをJava 21で起動する。
4. `config/jev-control.json` が作成され、`/jev status` が利用できることを確認する。

最初の検証は別の平坦なテストワールドで行うと結果を確認しやすい。同梱依存だけで起動できるため、
新規検証環境の `mods/` はこのJAR一つでよい。既存環境で他のCarpet/Fabric APIが入っている場合は、
そのversionが依存条件に合う必要がある。異なるMinecraft versionでの動作は保証しない。

## 3. Jevを設定

サーバー側の `config/jev-control.json` の `apiKey` を設定する。
リポジトリの `.env` はJARへ埋め込まず、自動転送も行わない。サーバーにはサーバー側の設定が必要。

初回生成内容:

```json
{
  "apiKey": "",
  "model": "jev-1.13.0",
  "actionTicks": 4,
  "timeoutSeconds": 10,
  "maxObservationAgeTicks": 200,
  "maxDecisions": 200,
  "maxRunSeconds": 600,
  "observationRadius": 3,
  "goalRadius": 1.0,
  "maxDistanceFromSpawn": 64.0
}
```

- `apiKey`: 自分のTypeSafe APIキーを入力する。
- `model`: 利用可能な固定version。`jev-latest`は受け付けない。
- `actionTicks`: 1回の移動入力を保持するtick数。初期値4＝20 TPS時0.2秒。
- `timeoutSeconds`: API応答の待ち時間上限。
- `maxObservationAgeTicks`: 回答が適用可能なsnapshot年齢の上限。
- `maxDecisions` / `maxRunSeconds`: runの上限。到達しなくても無期限に課金・移動しない。
- `observationRadius`: 局所block観測の水平半径。高さ方向は足元block基準で-1～+2。
- `goalRadius`: 実際の位置から目標までの到達判定半径。
- `maxDistanceFromSpawn`: 実験の移動範囲上限。超過はERROR停止。

設定はrun開始時に読み直すため、停止中の編集はサーバー再起動不要。必須項目の欠損・不正値はERRORになる。
APIキーなしでも次の身体診断は動作する。`/jev start`だけがキーを要求する。

## 4. キー不要の身体診断

OP権限で、足場が平坦で前方に数blockの空間がある場所から実行する。座標省略時は実行者の位置と向きに生成する。
コンソールからは `/` を付けず、spawn座標を明示する。

```text
/jev spawn
/jev status
/jev observe
/jev smoke
```

`spawn`後は1秒程度待って接地してから`smoke`を実行する。
`smoke`は **Jevを使わない診断** で、8tick前進し、入力を解除して慣性が落ち着いた後の静止を検査する。
数秒後に `/jev status` で `SMOKE_PASSED` を確認する。壁や水流、押してくるentityがある場合は失敗し得る。

任意の有限入力も確認できる:

```text
/jev step TURN_LEFT
/jev step FORWARD
```

これらはtrace上で `MANUAL_NO_MODEL` と記録され、Jevが選択した行動としては扱わない。

## 5. Jevの閉ループを実行

たとえばBotが `100.5 65 100.5` にいる場合、平坦な足場上の近い目標を指定する:

```text
/jev goal 100.5 65 106.5
/jev start
/jev status
```

`goal`には `~ ~ ~` の相対座標も指定できる。相対座標の基準はコマンド実行者であり、Botではない。
目標はBotと同じdimensionの座標として解釈する。

Jevは `WAIT / FORWARD / BACK / STRAFE_LEFT / STRAFE_RIGHT / TURN_LEFT / TURN_RIGHT / JUMP_FORWARD` から選ぶ。
旋回は15度、ジャンプは接地時のみ候補に入る。自動経路探索・自動回避・自動ジャンプ補完は接続していない。
Jevが壁へ向かう選択を続けた場合は、その結果を観測して再判断する。到達できること自体は実機評価の対象。

サーバーはAPI待ち中も動く。1入力を有限tickで解除した後に次の観測・問い合わせを行うので、
API待ち中に前回の前進が保持され続けることはない。重力や慣性を消して静止させる処理ではない。

停止と撤去:

```text
/jev stop
/jev despawn
```

サーバー再起動後にrunを自動再開する機能はない。再度spawnとgoalを指定する。

## コマンド一覧

| コマンド | 用途 |
|---|---|
| `/jev` | ヘルプ |
| `/jev spawn [x y z]` | 管理対象を1体生成。既存の同名playerを乗っ取らない |
| `/jev goal x y z` | 停止中に既知目標を設定 |
| `/jev start` | 設定とAPIキーを検証しJev run開始 |
| `/jev status` | 状態、理由、実行中decision数、traceファイル |
| `/jev observe` | 停止中の観測を保存。API呼出しなし |
| `/jev smoke` | 移動・停止の身体診断。API呼出しなし |
| `/jev step ACTION` | 短い入力を手動実行。API呼出しなし |
| `/jev stop` | 入力解除、未完了判断を取消 |
| `/jev despawn` | run停止と管理対象の撤去 |

すべてOP level 2以上が必要。管理対象は同時に1体。

## ログと判定

`logs/jev-control/<run-id>.jsonl` に以下を記録する:

- runのmodel、設定（APIキー除外）、MOD version、dimension、初期位置・目標
- 観測、可視cell/entity、候補集合と除外理由
- Jevのchoice・probabilities・confidence、API latency
- 実際に適用した入力、指定tick数、実行tick数
- 入力後の実位置、移動量、health、衝突状態、最終結果

| status | 意味 |
|---|---|
| `WAITING_FOR_POLICY` | 有限入力は解除済み。Jev回答待ち |
| `APPLYING` | 選択した有限入力を適用中 |
| `GOAL_REACHED` | 実位置が到達半径内 |
| `BUDGET_EXCEEDED` | decision数または時間上限。成功とは扱わない |
| `ERROR` | stale応答、不正response、HTTPエラー、設定・実行異常など |
| `DEAD_OR_DISCONNECTED` | Botが死亡または消失 |
| `CANCELLED` | 人またはサーバー停止による取消 |
| `SMOKE_PASSED` / `MANUAL_COMPLETED` | モデル不使用の診断結果 |

APIエラー、timeout、候補外actionをルールやWAITへ代替しない。停止して理由を返す。
HTTPエラー本文やAuthorization headerをログへ保存しない。

`UNKNOWN`は壁の向こう/未読込を表しairとは区別する。観測は距離とline of sightで制限し、カメラ視野角では制限しない。
他playerの名前・非公開inventory・health・意図をJevへ渡さない。現段階は直前の結果だけを持ち、長期記憶は持たない。

## 検証範囲

CIは同じ配布JARを空の `mods/` に配置したFabricサーバーを起動し、spawn、観測、
物理移動、入力解除、キー欠損の拒否、取消、despawn/再spawn、終了を検査する。
unit testはHTTP成功/401/timeout、不正回答、古い判断・取消済み判断、設定不備を検査する。

実Jevへの接続、実Jevでの100cycleと目標達成、障害物への適応はAPIキーを持つローカル環境で確認する。
CIの身体診断はJevの攻略能力の証明ではない。これらの実測はIssue #38へ記録する。
