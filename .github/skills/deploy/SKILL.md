---
name: deploy
description: JevControlのPaper JARを共有テストサーバーpluginsへSFTP配置し、バックアップとリモート再取得SHA-256で検証する。
---

# Deploy

`deploy.local.env.example` を参考にGit管理外 `deploy.local.env` または環境変数でSFTP接続情報を設定する。Posh-SSHが必要。初回のSSHホスト鍵は別途照合して信頼済みにする。

```powershell
tools/runtime/remote.ps1 -Action Preflight
tools/runtime/remote.ps1 -Action Deploy -Plan
tools/runtime/remote.ps1 -Action Deploy
```

既定の配置先は `/test_server/plugins/jev-control-paper.jar`。既存JARのバックアップは `.runtime-harness/remote-<id>/` に保存する。stageへ転送して再取得ハッシュを確認後に置換し、最終パスを再取得して再検証する。別名のJev JARがある場合は自動削除せず停止する。
成果物の配置はactivationとは別。実サーバーを変更せず「デプロイできる状態」を求められた場合は `-Plan` とread-only preflightまで。
