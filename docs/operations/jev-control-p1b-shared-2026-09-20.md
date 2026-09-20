# Issue #40：共有サーバーへの配置と実Jev検証

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。[隔離Paperの55試行](jev-control-p1b-live-evaluation-2026-09-20.md)は保持する。ユーザーの追加指示により、共有環境での配置・稼働・実検証までを完了条件とし、先のcloseを訂正してreopenした。

**結果：共有サーバーへの配置・activation・実Jevの4方向到達と取消1件・生trace監査を完了した。** 稼働JARは隔離評価の最終artifactと一致する。5runで11判断、12 API requests、49入力tick、run時間合計9.723秒。全run後の水平速度0、生存、despawn、最終bot不在、常設認証の保持を確認した。[公開指標と証跡ハッシュ](jev-control-p1b-shared-results-2026-09-20.json)。

## 実行前の計画・受入条件

配置対象は隔離比較で9/9到達したsource `aebad6f`、JAR SHA-256 `d2efa94f3cb5def7a15cf6212614c1e27e4c3092989aedeff4a36a244c9afd02`。新しいplugin実装を混ぜない。既存JARをバックアップし、転送後の再取得ハッシュ、activation marker以降のJEV_READY、statusの稼働ハッシュを一致させる。

事前確認：共有 `/test_server/plugins` にJev JARは1個、LastOrderあり。旧稼働ハッシュ `ccd880f347345c2e81415fd77e11162a7f17df34512b62f4ce4433c6b6222c54`、botなし。常設Jevキーはconfigured、sealed RSA、config/private key各600・directory700。設定やキーを読み出さず `key-status` を使用する。

オンラインPhilia_Gray付近の検査済み3×7平坦レーンをrunごとに再選定する。地形は変更しない。`assisted`で南3block・東1.25block・西1.25block・北1.25blockの4到達runと、南5blockへ動作中の取消1run。後者は最初の判断が実行されてからstopする。各run60判断/120秒/240入力tick以下、全5run最大300判断/600秒/1,200入力tick。到達半径1、model jev-1.13.0。短い横方向目標は、安全検査済みレーン内で軸の選択と実移動を確認するためであり、長距離の横移動性能ではない。

受入条件は4到達、取消runのCANCELLED、全runが実Jev・assisted・配置JAR一致、候補→判断→固定終点→毎tick入力→実座標→停止の整合性、停止後の水平速度0.001未満・生存・despawn・最終botなし、認証設定保持。成功文字列だけで合格とせず、生traceを既存P1b verifierと共有用manifest検証で再計算する。失敗も保存し、再試行前に原因と追加計画を記録する。

共有での人工的な壁追加・地形改変は行わず、壁3条件の評価は隔離試験として区別する。共有環境の他pluginエラーはJevの結果と別に記録する。

## 結果・未達条件

初回Preflightは専用worktreeにSFTP環境変数がなく失敗したが、既存の共有サーバー接続設定をメモリに読み、宛先が `/test_server/plugins` であることを確認して解決した。認証値は報告・証拠へ保存しない。

配置後の再取得SHA-256、activation marker以降のJEV_READY、起動後statusのSHA-256がすべて対象JARと一致した。旧JARのSHA-256も事前稼働版と一致し、ローカルにバックアップ済み。Jev statusはIDLE/botなしで起動し、key-statusは配置前後で同じ常設認証・権限を示した。

共有実験source `30d4bb3`（harness追加のみ。plugin実装sourceは `aebad6f`）、証拠 `.runtime-harness/remote-p1b-shared-aa2b16f5d329/`。runごとに安全レーンを再検査した結果、全件のspawnは `(-17.5,-60,2.5)`、worldは `world`。最初の事前確認時とは参照プレイヤーの位置が変化したため、古い座標を再利用していない。

| 条件 | 終了 | Jev選択 | 判断数 | 入力tick | run秒 | 終了時の目標距離 |
|---|---|---|---:|---:|---:|---:|
| 南3block | GOAL_REACHED | S×3 | 3 | 13 | 2.444 | 0.8688 |
| 東1.25block | GOAL_REACHED | E | 1 | 5 | 1.095 | 0.5162 |
| 西1.25block | GOAL_REACHED | W | 1 | 5 | 1.095 | 0.5162 |
| 北1.25block | GOAL_REACHED | N | 1 | 5 | 1.095 | 0.5162 |
| 南5block・取消 | CANCELLED | S×5 | 5 | 21 | 3.994 | 1.3149 |

取消は5区間の実移動後、第6requestの応答待ちにstopが届いた。6 API requestsに対して判断は5件、取消後の判断適用・追加入力なし。**共有での区間入力途中の取消を観測した結果ではない。** そのケースは隔離Paperの検証として区別する。共有では取消後に2秒待って身体を再観測し、水平速度0・health20を確認した。

P1b verifierで全segmentのschema、候補・固定点・yaw/入力強度・距離/時間上限・実身体tick・到達・terminalまでの連続性を再計算した。共有用auditはplan/evaluatorハッシュ、実行順、server receipt、spawn/goal/稼働JAR/実Jevモード、同じbotの終了後観測、認証の前後一致と後始末を検証しPASS。全5件の再実行や成功への差し替えは行っていない。receipt parser2テスト、既存P1b verifier11テストもPASS。

## 他プラグインの状態と制限

activationのreloadでは、LastOrder gatewayのAddress already in use、pdf_to_map HTTP gateway起動失敗、PacketEvents系のDuplicate handler nameを記録した。同じ生ログの今回markerより前にも、それぞれ5件・5件・12件の記録があり、今回のmarker以降は1件・1件・3件だった。これは既存にも同種エラーがあるという観測事実であり、今回のJev更新が原因でないと断定する材料ではない。Jevのready、受信口、実API、身体動作、後始末は確認できたが、共有サーバー上の全プラグインが正常とは報告しない。別pluginの設定変更やreloadの反復は行っていない。

Issue #40に追加された共有配置・実稼働・実検証の条件に未達はない。人工壁3条件の共有再現、未知地形への汎化、他plugin全体の修復は未実施。地形と常設キー設定は変更せず、試験botはすべて除去し、配置済みJARは稼働状態で残した。

## 再現・証跡

既存のSFTP設定を環境変数へ読み込み、既に検証したartifactを使用する。秘密値をコマンド引数へ入れない。

```powershell
tools/runtime/remote.ps1 -Action Preflight
tools/runtime/remote.ps1 -Action Deploy -RunId <配置ID>
tools/runtime/remote.ps1 -Action Reload -RunId <activationID>
python tools/runtime/shared_p1b.py --player Philia_Gray --execute
python tools/runtime/shared_p1b.py --audit-directory .runtime-harness/remote-p1b-shared-aa2b16f5d329
python -m unittest discover -s tools/runtime -p test_shared_p1b.py
```

配置証跡は `remote-p1b-shared-deploy-20260920/`（旧JAR含む）、activation生ログは `remote-p1b-shared-activate-20260920/activation.raw.log`。初期・起動後status/key-statusはそれぞれ `remote-p1b-shared-before-20260920/` と `remote-p1b-shared-after-20260920/`。実験の `plan.json`、`shared-experiment.json`、`shared-audit.json`、trace/receipt/取得ログを保持する。manifestのPENDING_AUDITは採取時の状態で、独立監査結果は `shared-audit.json` のpassed=true。

ローカル証拠は `C:/github_folder/minecraft-ai-jev-embodied-control/.runtime-harness/remote-p1b-shared-*/`。既存JARバックアップ、生trace、receipt、生ログはローカルのみ、公開報告には必要な指標・ハッシュと所在を記載する。
