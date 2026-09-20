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

## Issueタスクの終了時報告（必須）

Issueに紐づく実験では、ルート `AGENTS.md` の「Issueに紐づくタスクの必須報告」を終了条件として適用する。対象Issueと受入条件を実行前に確認し、終了時は次の順序で報告する。

1. 成功・失敗・中断を含む全試行の証跡を保存し、再現手順・設定・source/model/artifact・予算・停止理由・後始末の結果を報告書にまとめる。問題は観測された事実と原因仮説を分け、比較結果と未解決点を書く。
2. 対象Issue本文に結論、受入条件ごとの達否、問題の要約、報告書への直接リンクを追記する。小規模な作業ではIssue本文を報告書としてよい。`verification.json` の生成だけでこの手順を完了したと扱わない。
3. Issueの反映を読み戻して確認する。最終回答にも報告書とIssueへの直接リンクを必ず含める。更新できない場合はローカル報告書の場所と同期未完了を明記する。

ローカルテストやCIの成功は実機目標の達成と区別する。受入基準未達なら失敗のFindingを残し、成功としてIssueをcloseしない。

## 実Jevと障害試験

常設済みサーバーでは `tools/runtime/live-near-player.ps1 -UseConfiguredKey -Player Philia_Gray -Execute` を使用する。設定・キーは読出し/上書き/復元せず、`jev key-status` の非秘密情報で構成を確認する。終了時はこの試験のbotだけstop/despawn。以下の一時キー手順を常設サーバーへ適用しない。常設・ローテーションは `deploy/SKILL.md` の暗号化provision手順へ。

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

## P1a: 動的障害物と目標への復帰

Issue #39の条件と総予算は `docs/operations/jev-control-p1a-plan-2026-09-20.md`。P0の成功判定ではP1aを判定しない。実API実行を許可された場合、隔離Paperで次を使う:

```powershell
python tools/runtime/p1_acceptance.py --phase baseline --repeats 3 --artifact <保存したP0のJAR> --key-file <既存.envの絶対パス> --execute
python tools/runtime/p1_acceptance.py --phase development --repeats 1 --artifact build/libs/jev-control-paper-0.2.0.jar --key-file <既存.envの絶対パス> --execute
python tools/runtime/p1_acceptance.py --phase final --repeats 3 --artifact build/libs/jev-control-paper-0.2.0.jar --key-file <既存.envの絶対パス> --execute
python tools/runtime/p1_acceptance.py --audit-directory <p1a-evidence-directory>
```

実行前にartifact・条件・予算をplanへ保存する。baseline/developmentは失敗を含む比較資料、finalは同一JARで3条件×3回、各条件2回以上到達が必要。元の壁は左右対称なので、mirrored-wallは壁の体積のみをworld x=0で反転し、開始位置と目標を保持する。壁の観測→判断→入力→結果と実座標での到達をauditする。ERROR停止を別policyや再試行で埋めない。生trace・失敗結果を保存し、共有サーバーの地形は変更しない。
