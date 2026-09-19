# Jev embodied control

このブランチはIssue #37/#38のPaperプラグイントラック。対象は共有サーバー起動設定のPaper 1.21.11 build 116 / Java 21。Fabric版の過去の証拠をPaper版の合格として使わない。

繰り返し操作は `.github/skills/` の該当SKILL.mdを読んで実行する:

- build: `build/SKILL.md`
- deploy: `deploy/SKILL.md`
- reload: `reload/SKILL.md`
- commands: `execute-server-command/SKILL.md`
- server logs / JSONL: `get-server-log/SKILL.md`
- repeated experiments: `runtime-experiment/SKILL.md`

実装の不変条件: メインスレッドでworld読取・入力適用、Jev HTTPは非同期、一体一判断、有限tick入力、取消後の遅着回答破棄。API失敗を別policyやWAITへ置換しない。経路探索・velocity直書き・移動teleportを操作に追加しない。

変更後は `tools/runtime/build.ps1 -Smoke`。実Jev評価は3run/100cyclesを別に実施して証拠を残す。`deploy.local.env`、APIキー、取得した生ログはコミットしない。
