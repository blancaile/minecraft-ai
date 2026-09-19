---
name: runtime-experiment
description: Jevのデプロイ・reload・実験コマンド・結果待ち・ログ回収・bot後始末をシナリオで再現し、観測に基づく修正と再検証を進める。
---

# Experiment loop

関連skillのbuild/deploy/reload/execute-server-command/get-server-logを必要な操作に応じて読む。
最初に共有サーバーで実験してよい平坦な領域とworldを特定し、`tools/runtime/smoke.example.json`をベースにシナリオを作る。サンプル座標を共有サーバーの空き地と仮定しない。

```powershell
tools/runtime/build.ps1 -Smoke
tools/runtime/experiment.ps1 -Scenario tools/runtime/smoke.example.json -Deploy -Reload
tools/runtime/experiment.ps1 -Scenario tools/runtime/smoke.example.json -Deploy -Reload -Execute
```

`-Execute`なしはplanのみ。実行すると既存bot不在を確認し、各commandは一度だけ送信する。非同期結果はstatusで最大30秒待つ。途中失敗時にも、この実験で生成したbotをstop/despawnし、ログとtraceを回収する。後始末失敗もrun失敗として記録する。

実験→仮説→最小修正→unit/smoke→同じ実験の順で進める。診断用ログを追加した場合は `RUNTIME-DIAG` を付け、修正後に削除してbuild検査を通す。実Jev runでは事前固定の予算・全run結果・未達条件を残し、APIキーや認証headerは証拠に含めない。
同じ症状で新しい証拠が得られない場合は、reloadを反復せず、manifest・receipt・traceを使って仮説を見直す。
