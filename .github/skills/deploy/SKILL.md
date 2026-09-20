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

## 常設Jevキー（明示承認された場合のみ）

```powershell
tools/runtime/provision-credential.ps1 -KeyFile <既存.envの絶対パス> -Execute
tools/runtime/remote.ps1 -Action Command -Command 'jev key-status'
```

対応JARを反映してから実行する。既存README loaderからキーをメモリへ読み、サーバー公開鍵の所有者・置換防止権限を照合後、RSA-3072 OAEP SHA256/MGF1-SHA256で暗号化。SFTP受信口に渡すのは暗号文だけで、平文のコマンド/設定/一時ファイルは作らない。サーバー自身がconfigを暗号文・600、復号秘密鍵を600、secretsディレクトリを700で保存する。公開鍵とdataディレクトリは他OSユーザーから書換不可にする。

SFTPユーザーとJavaのUIDが違う環境で、SFTP作成の600秘密ファイルをJavaが読めると仮定しない。権限が実現できない場合は停止し、読み取り可能へ緩めない。POSIX非対応環境ではこの機能を拒否し、明示的なサーバー環境変数を使う。秘密鍵を失うと暗号文を復号できないため、サーバー所有者の保護されたバックアップが必要。

キーを消して試験前の空設定へ戻さない。常設後の試験は `live-near-player.ps1 -UseConfiguredKey`。SFTPからconfig/private keyを読めなくなるのは正常。`key-status`のconfigured/storage/権限表示と実Jevの判断/移動で検証する。

この保護は別OSユーザーに対するもの。root、サーバー所有者、同一Paperプロセスのプラグイン、保護なしのバックアップからは隔離しない。暗号化を「他のプラグインから絶対に隠せる」と説明しない。
