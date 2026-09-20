# Jev embodied control

このブランチはIssue #37のPaperプラグイントラック。#38はP0完了、#39はP1a到達基準未達の比較記録。次の主作業は#40（Jevの近距離移動判断＋有限区間の実行補助）。対象は共有サーバー起動設定のPaper 1.21.11 build 116 / Java 21。Fabric版の過去の証拠をPaper版の合格として使わない。

繰り返し操作は `.github/skills/` の該当SKILL.mdを読んで実行する:

- build: `build/SKILL.md`
- deploy: `deploy/SKILL.md`
- reload: `reload/SKILL.md`
- commands: `execute-server-command/SKILL.md`
- server logs / JSONL: `get-server-log/SKILL.md`
- repeated experiments: `runtime-experiment/SKILL.md`

実装の不変条件: メインスレッドでworld読取・入力適用、Jev HTTPは非同期、一体一判断、有限tick入力、取消後の遅着回答破棄。API失敗を別policyやWAITへ置換しない。経路探索・velocity直書き・移動teleportを操作に追加しない。

変更後は `tools/runtime/build.ps1 -Smoke`。実Jev評価は有効なIssueの条件・事前固定した予算に従い、P0の3run/100cyclesを後続の合格条件へ流用しない。`deploy.local.env`、APIキー、取得した生ログはコミットしない。

## 補助付き制御の境界

#40の設計・実装では `docs/research/jev-assisted-control-plan-2026-09-20.md` を読む。Jevが近距離の移動先・継続・後退を選び、コードは選択済み区間の入力変換・補正と距離/時間/衝突による解除を担当できる。区間途中に別の目的地や迂回先を選ばず、再判断が必要なら結果をJevへ返す。既存direct方式を比較用に保持し、run途中の自動切替をしない。旧#39の制御境界と受入結果は過去の評価契約として保存する。

## Issueに紐づくタスクの必須報告

Issueに紐づく調査・実装・評価では、成功・失敗・中断を問わず、終了報告前に以下を完了する。

- 対象Issueを明記した報告書を作成または更新する。目的・受入条件、変更内容、実施した検証と結果、失敗・未達条件、確認済みの事実と原因仮説、未解決点、再現手順、commit・証跡の参照先を記載する。未実施・不明な項目はその旨を書く。
- 報告書は原則 `docs/operations/` に保存する。小規模な作業では同じ内容をIssue本文へ直接記載してもよい。生ログや成功表示だけを報告書の代わりにしない。秘密情報を含めず、ローカルにのみ存在する証跡は保存場所と公開範囲を明示する。
- 対象Issue本文に結論・未達条件・報告書への直接リンクを追記し、受入条件と状態を実結果に合わせる。評価の実施完了と目標達成を区別し、基準未達を成功としてcloseしない。
- Issueの更新を読み戻して確認し、最終回答にも報告書とIssueへの直接リンクを載せる。外部更新が失敗した場合は報告書をローカルに保存し、同期未完了を明記する。同期できるまでは報告まで完了したと扱わない。
