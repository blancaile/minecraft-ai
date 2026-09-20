# JevControl Paper: build, deploy and observe

対象は **Paper 1.21.11 build 116 / Java 21**。共有サーバーの起動設定に合わせた単一プラグインJARです。参加者のクライアントMOD、Fabric、Carpet、Citizensは不要です。Spigot単体、Folia、他のMinecraft版は未対応です。

旧Fabric版の配布物は `be2833f8` の履歴に残ります。0.2.xは `mods/` へ配置しません。

検証済み項目・配布JARハッシュ・未達項目は[Paper移植検証記録](jev-control-paper-verification.md)を参照してください。

## ビルドとローカル実機検証

```powershell
.\tools\runtime\build.ps1 -Clean -Smoke
```

成果物: `build/libs/jev-control-paper-0.2.0.jar`。
Java 21、Gradle 9.4.0、paperweight 2.0.0-beta.23、開発bundle `1.21.11-R0.1-20260215.191825-75` を使用します。
Linux/macOS: `./gradlew clean build` → `python3 tools/ci/server_smoke.py build/libs/jev-control-paper-0.2.0.jar`。

smokeは `.runtime-harness/paper-smoke-<id>/` に隔離Paperサーバーを作り、既存fixtureのEULA確認を引き継ぎます。Paper JARの固定SHA-256を検証し、loopbackだけで起動します。実Jev APIは呼びません。

生成、重力、有限入力、壁との衝突、旋回、ジャンプ、入力解除、キー欠損拒否、取消、despawn、reload時のbot除去、再生成、SFTP受信口のreceipt/期限切れ/対象外コマンド拒否を試験します。`verification.json`、`console.log`、`plugins/JevControl/traces/*.jsonl` が証拠です。

## 配置と反映

各処理のskillは `.github/skills/`。最初に `deploy.local.env.example` をGit管理外の `deploy.local.env` へコピーし、既存のSFTP接続情報を設定します。環境変数を優先します。Posh-SSHと照合済みのSSHホスト鍵が必要です。

```powershell
.\tools\runtime\remote.ps1 -Action Preflight
.\tools\runtime\remote.ps1 -Action Deploy -Plan
.\tools\runtime\remote.ps1 -Action Deploy
```

既定の配置先は `/test_server/plugins/jev-control-paper.jar`。旧JARはローカルへバックアップし、stageと最終配置先を再取得してSHA-256を検証します。配置だけでは反映済みとは判定しません。

Paper公式は更新時にサーバー再起動を推奨しています。共有テストサーバーでreload運用を使う場合:

```powershell
.\tools\runtime\remote.ps1 -Action Reload
.\tools\runtime\remote.ps1 -Action Command -Command 'jev status'
```

LastOrderへ `bukkit:reload confirm` を送信し、今回のmarker以降の `JEV_READY` に配置JARと同じSHA-256があることを確認します。reloadは他プラグインにも作用します。`/reload` や `/paper reload` がJevのJAR更新と同義とは仮定しません。

## キーなし身体実験

実JevのキーはREADME記載の `.env` の `jev_api_key` を既存loaderで取得できます。繰り返し検証には `.github/skills/runtime-experiment/SKILL.md` のlive手順を使います。隔離サーバーでは `apiKey: "env:JEV_API_KEY"` を指定し、キーを設定ファイルへ保存せず子Javaプロセスの環境変数から読みます。共有サーバーの短い試験は元設定を終了時に復元します。

特定のオンラインプレイヤーの近くで試験してよい場合は、`jev site PLAYER`で現在位置と近傍の候補を読み、`jev spawn-near PLAYER`で生成直前に再検査できます。現在位置の水平10ブロック・上下3ブロック以内で、ロード済みの3x7の平坦な通常ブロック床、3ブロック高の空間、entity不在を確認します。地形変更やプレイヤー移動はしません。条件を満たす場所がなければ停止します。

```powershell
.\tools\runtime\experiment.ps1 -Scenario tools/runtime/near-player.example.json -Execute
```

サンプルの`Philia_Gray`は今回許可された対象です。別の試験では許可された対象に変更してください。場所選定は試験準備のみで、Jevの移動policyには使いません。
シナリオの`verification: near-player-smoke`は、回収JSONLとreceiptのハッシュ、初期位置、実移動量、8tick入力、停止時水平速度、15度旋回、生存を自動検査し、`verification.json`を残します。

検証してよい平坦な領域を選び、前方に空間を確保します。共有サーバーで下記のサンプル座標をそのまま使わないでください。コンソールの場合は座標と必要ならworldを指定します。

```text
/jev spawn 0.5 81 0.5 world
/jev status
/jev observe
/jev smoke
/jev status
/jev step TURN_LEFT
/jev stop
/jev despawn
```

spawn後に接地してからsmoke。8tick前進し、慣性が落ち着いた後の静止を確認します。`SMOKE_PASSED` はJev能力の評価ではありません。停止は入力を解除し、重力や慣性は維持します。

## コマンド実行とログ

```powershell
.\tools\runtime\remote.ps1 -Action Command -Command 'jev status'
.\tools\runtime\remote.ps1 -Action Log -RunId probe-1
.\tools\runtime\remote.ps1 -Action Traces -RunId probe-1
```

Jevコマンドは `plugins/JevControl/inbox/<UUID>.json` に完成ファイルをrenameで投入し、`receipts/<UUID>.json` の実行結果を待ちます。ID、コマンド、期限を検査し、Jev以外の操作を受け付けません。受信口の書込権限は管理者だけにしてください。期限切れ、disable後、処理済みIDは再実行しません。タイムアウト時は結果不明なので自動再送しません。smoke/startは受付後にstatus/traceで終了を確認します。

他のコンソールコマンドは `-Transport LastOrder -Command '...'`。既存allowlistに従い、投入結果は `QUEUED_NOT_VERIFIED` として返します。実結果をログで確認します。

生ログは `.runtime-harness/remote-<id>/` へそのまま保存し、サーバー側のログは変更しません。詳細な観測・判断・入力・物理結果は専用traceに記録し、一般サーバーログは起動/終了とterminal結果が中心です。

## 繰り返す実験ハーネス

配置・反映後、場所が未確定でもコマンド往復と証拠回収だけは以下で確認できます（botは生成しません）:

```powershell
.\tools\runtime\experiment.ps1 -Scenario tools/runtime/status.example.json -Execute
```

`tools/runtime/smoke.example.json` の座標とworldを対象の検証場へ変更したシナリオを用意します。

```powershell
.\tools\runtime\experiment.ps1 -Scenario <scenario.json> -Deploy -Reload
.\tools\runtime\experiment.ps1 -Scenario <scenario.json> -Deploy -Reload -Execute
```

既定はplanのみ。`-Execute`で配置→反映確認→コマンド→期待状態待ち→stop/despawn→log/trace回収を実行します。既存botを奪わず、この実験で生成したbotだけを後始末します。`experiment.json` に結果と後始末の失敗も保存します。

JARが変わらない反復では`-Deploy -Reload`を省略します。Jevのready成功と共有サーバー全体の健全性は別です。reloadログに他プラグインのERRORがあれば記録し、無条件にreloadを繰り返さないでください。初回実験前のtrace未作成は0件として回収します。

原因調査で一時ログを追加するなら `RUNTIME-DIAG` を付け、修正後にすべてソースから除去します。buildスキルとCIは残存を拒否します。再ビルドと同じ実験を通して通常ログの状態に戻します。他プラグインのログや過去の証拠を全消去する処理はありません。

## 実Jev

初回起動で作成する `plugins/JevControl/jev-control.json` の `apiKey` を設定し、固定model/versionと予算を確認します。設定はrun開始時に再読込し、キーはtraceへ保存しません。

```text
/jev spawn
/jev goal ~ ~ ~5
/jev start
/jev status
/jev stop
/jev despawn
```

相対座標はコマンド実行者が基準です。goalはbotと同じworldに限定します。API待ちは非同期、一体一判断。timeout/stale/不正応答では入力を解除してERROR停止し、別policyへ切り替えません。

Issue #38の実Jev 3run/100cycles、目標到達、障害物による再選択は別の未達条件です。ローカル身体smokeで代替できません。またNMS fake playerは通常のログイン/移動パケット経路と同一ではなく、共有環境の保護・NPC判定・アンチチート等との相互作用は現地で検証が必要です。
