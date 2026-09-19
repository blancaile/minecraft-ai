# Paper migration verification — 2026-09-19

ローカル作業ブランチ: `feat/jev-embodied-control`。移植元: `be2833f8de8c4a773992fadd08c08a44e285e038`。以下は旧Fabric版CIとは別の、Paper配布JARのローカル検証結果。

## 配布物と対象

- JAR: `build/libs/jev-control-paper-0.2.0.jar`
- SHA-256: `40905a11898d31d719ad03f982d4f99c93615f418fb7fd2a270f7df87e4f9bf1`
- Paper: Minecraft 1.21.11 build 116 / Java 21
- Server JAR SHA-256: `e708e8c132dc143ffd73528cccb9532e2eb17628b1a0eee74469bf466c7003f8`
- 開発bundle: `1.21.11-R0.1-20260215.191825-75`
- `plugin.yml`を持つ単一JAR。Fabric/Carpet/Minecraft/Bukkitのクラスは同梱しない。

## 実行と結果

```powershell
tools/runtime/build.ps1 -Clean -Smoke
```

**PASS**。unit test 11件、ネットワークなしのデプロイ模擬試験6件、隔離Paper実サーバーの20項目を通過。

実サーバー証拠: `.runtime-harness/paper-smoke-888daad2e920/`

- `verification.json`: 対象JARハッシュ、20項目、`model_invoked: false`
- `console.log`: 起動、コマンド、NMS entityの実座標、reload、終了
- `plugins/JevControl/traces/*.jsonl`: 観測、入力、物理結果、terminal
- `plugins/JevControl/receipts/*.json`: ファイル受信口の実行結果

確認した挙動:

- spawn → 8tick前進 → 入力解除後の静止。ゲーム側の位置は `(0.5,81,0.5)` から `(0.5,81,2.0073124058050658)`。
- y=84から重力でy=81へ着地。壁を通り抜けず`BLOCKED`を記録。旋回-15度、ジャンプの上昇、結果の4/8tick境界、遮蔽セルの`UNKNOWN`を検証。
- APIキー欠損時は拒否。取消、despawn、再生成を検証。
- botがいる状態でreloadし、disable後に`bot=none`、同じJARハッシュで再enable、再生成・再移動に成功。
- SFTPと同じファイル受信口で成功receipt、期限切れ拒否、Jev以外のコマンド拒否を検証。
- デプロイ模擬試験は旧JARバックアップ/置換、重複JAR拒否、転送ハッシュ不一致時の旧JAR保持、rename失敗時の復旧、不許可コマンド拒否、LastOrderの投入結果と実行結果の区別を検証。
- 6スキルの形式検証、PowerShell構文検証、実験/配置のplan、`git diff --check`も成功。一時診断ログのmarkerは`src/main`に残していない。

## 共有サーバーと未検証項目

SFTPで共有サーバーの起動設定が`paper-1.21.11-116.jar`を参照することを読み取り確認。`/test_server/plugins`とLastOrder、ログ取得を確認した。read-only preflightの証拠は`.runtime-harness/remote-paper-readonly-preflight/`。

このローカル試験の時点では共有サーバーへのJAR配置、reload、bot生成は未実施。その後の配置・反映確認は下記を参照。fake playerは通常クライアントのログイン/移動パケット経路と同一ではなく、保護・アンチチート等との互換性を一括保証しない。

実Jev APIは使用していない。#38の3run/100cycles、到達と障害物適応、実サーバー上でのAPI障害注入は未達。Issue #37/#38はopenを維持する。Paper版のCIは設定を更新した段階であり、このローカル結果を新しいCI成功と表現しない。

配置・反映・実験の再現手順は[quickstart](jev-control-quickstart.md)と`.github/skills/`を参照。詳細traceを専用ファイルへ分離し、一時診断出力だけをソースから除去する。共有サーバーの過去ログや他プラグインの記録は消去しない。

## 共有サーバーへの初回配置・ハーネス実行（同日）

ユーザーの実行許可後、コミット`cea251d642d012ae65e6f103cd63e7088834be17`の上記JARを`/test_server/plugins/jev-control-paper.jar`へ配置し、再取得SHA-256一致を確認した。旧Jev JARはなかった。

- `remote.ps1 -Action Deploy` → `verified: true`
- `remote.ps1 -Action Reload` → LastOrder経由でmarker確認後に`bukkit:reload confirm`を1回送信。
- 21:01:18の`JEV_READY`に同じSHA-256を確認。21:01:19に`Reload complete`。
- `remote.ps1 -Action Command -Command 'jev status'` → ID付き成功receipt、`state=IDLE bot=none`。
- 証拠: `.runtime-harness/remote-live-20260919-first/`の`Deploy.json`、`Reload.json`、`activation.raw.log`、`latest.raw.log`、receipt。

初回trace回収で、実験未実施のため`traces/`が存在せずエラーになる不具合を発見した。ハーネスを修正し、JevControlのdataディレクトリが存在する場合だけ、未作成traceを正常な0件として扱う。dataディレクトリもなければ失敗を維持する。回帰試験を加えてデプロイ模擬試験は**7件PASS**。JARは変更しておらず、この修正で再reloadは行っていない。

```powershell
tools/runtime/experiment.ps1 -Scenario tools/runtime/status.example.json -Execute
```

実行結果: **PASSED**。ID: `8eb4ecc8-9134-408d-8971-e7935cf41f19`。コマンド往復・期待状態確認・生ログ取得・空trace回収が成功し、`cleanup_errors`と`evidence_errors`は空。
証拠: `.runtime-harness/remote-8eb4ecc8-9134-408d-8971-e7935cf41f19/experiment.json`、`Log.json`、`Traces.json`、receipt。

これは配置・反映・コマンド・証拠回収の実機試験であり、**共有サーバー上の身体移動試験ではない**。bot生成・移動・実Jev呼出しは未実施。移動試験は許可されたworld/座標をシナリオへ設定してから行う。地形変更はしていない。

### reload時の共有環境の注意

Jevの起動と受信口は正常だったが、取得ログのmarker以降には13行のERRORがあった。データパックmetadata、他JARの`plugin.yml`、Paper command builderの`ConcurrentModificationException`、他プラグインのAPI設定等。これはJevの反映成功と分けて扱い、共有サーバー全体の健全性は宣言しない。無関係なプラグインや設定を修正せず、追加reloadも行っていない。実験・スクリプトのみを変える場合は`-Deploy -Reload`を省略し、JAR更新時だけ反映する。
