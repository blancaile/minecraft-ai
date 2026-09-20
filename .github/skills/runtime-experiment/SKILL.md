---
name: runtime-experiment
description: Jevのデプロイ・reload・実験コマンド・結果待ち・ログ回収・bot後始末をシナリオで再現し、観測に基づく修正と再検証を進める。
---

# Experiment loop

関連skillのbuild/deploy/reload/execute-server-command/get-server-logを必要な操作に応じて読む。
最初に共有サーバーで実験してよい平坦な領域とworldを特定し、`tools/runtime/smoke.example.json`をベースにシナリオを作る。サンプル座標を共有サーバーの空き地と仮定しない。
場所が未確定なら`tools/runtime/status.example.json`でコマンド往復と証拠回収だけを先に検証できる。これは身体の移動試験ではない。
ユーザーが特定プレイヤー付近を許可した場合は`tools/runtime/near-player.example.json`のプレイヤー名をその対象へ設定する。`site`→`spawn-near`で現在の地形とentity不在を確認する。場所選定はoperatorの試験準備だけであり、Jevの観測・行動選択には接続しない。
このシナリオはreceiptの成功だけでなく、回収したJSONLのJARハッシュ・初期位置・実座標差・8tick入力・停止時の水平速度・15度旋回・生存も検査し、`verification.json`を保存する。既存証拠は`tools/runtime/verify-near-player.ps1 -RunDirectory <証拠ディレクトリ>`で再検証できる。

```powershell
tools/runtime/build.ps1 -Smoke
tools/runtime/experiment.ps1 -Scenario tools/runtime/smoke.example.json -Deploy -Reload
tools/runtime/experiment.ps1 -Scenario tools/runtime/smoke.example.json -Deploy -Reload -Execute
```

`-Execute`なしはplanのみ。実行すると既存bot不在を確認し、各commandは一度だけ送信する。非同期結果はstatusで最大30秒待つ。途中失敗時にも、この実験で生成したbotをstop/despawnし、ログとtraceを回収する。後始末失敗もrun失敗として記録する。

実験→仮説→最小修正→unit/smoke→同じ実験の順で進める。診断用ログを追加した場合は `RUNTIME-DIAG` を付け、修正後に削除してbuild検査を通す。実Jev runでは事前固定の予算・全run結果・未達条件を残し、APIキーや認証headerは証拠に含めない。
同じ症状で新しい証拠が得られない場合は、reloadを反復せず、manifest・receipt・traceを使って仮説を見直す。

## 実Jevと障害試験

READMEの `.env` の `jev_api_key` は `tools/probes/jev_client.py::load_jev_api_key` で読む。キーの再入力をユーザーへ求める前にこの既存設定を確認する。値や認証header、`.env`の内容は出力・証拠保存・commitしない。実API呼出しの明示許可がある場合だけ `-Execute` / `--execute` を使う。

共有サーバーの許可されたプレイヤー近傍の短い実Jev試験:

```powershell
tools/runtime/live-near-player.ps1 -KeyFile <既存.envの絶対パス> -Player Philia_Gray -Execute
```

20判断/120秒、生成地点から南3ブロックの目標。元設定をメモリに保持して一時的にキーを供給し、最後にstop/despawn・設定復元・ログ回収する。設定はrun開始時に読むのでreload不要。強制終了・接続断時には設定復元を別途確認する。`GOAL_REACHED_PENDING_TRACE_VERIFICATION`はtrace検証前であり全受入合格ではない。SFTP `WriteAllText`は短い内容へ上書きしたとき末尾を残す場合があるため、設定書込みはtruncateするstreamを使う。

Issue #38の方向別反復・動的障害物と異常応答は隔離Paperで実行する（共有地形を変更しない）:

```powershell
python tools/runtime/paper_acceptance.py --mode faults --execute
python tools/runtime/paper_acceptance.py --mode live --key-file <既存.envの絶対パス> --execute
```

先にbuild/Smokeで固定Paperをキャッシュする。`--execute`なしで事前予算とfixtureを見る。証拠は `.runtime-harness/paper-{live,faults}-*/`。liveはキーを子Javaの環境変数だけに渡す。faultsはloopbackと専用ダミーキーだけで動き、本物のキーを読まない。APIエラーは再試行や別policyへ置換せず停止。初期姿勢のfixture設定はrun開始前のみ。全失敗runを残し、実Jevのcycleと模擬判断を合算しない。
