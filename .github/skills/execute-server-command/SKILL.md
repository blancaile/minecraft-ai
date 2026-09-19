---
name: execute-server-command
description: JevControlのSFTP受信口へコマンドを送りID付き実行結果を回収する。他の許可済みコンソールコマンドは共有サーバーのLastOrderキューから送る。
---

# Commands

```powershell
tools/runtime/remote.ps1 -Action Command -Command 'jev status'
tools/runtime/remote.ps1 -Action Command -Command 'jev spawn 0.5 81 0.5 world'
tools/runtime/remote.ps1 -Action Command -Command 'jev smoke'
```

受信口は `plugins/JevControl/inbox/<UUID>.json`。アップロード完了後のrenameで公開する。JSONはID、コマンド、期限を含み、期限切れやdisable後のコマンドは実行しない。処理済みIDは再実行しない。受信口へ書ける権限はサーバー管理者だけにする。
`receipts/<UUID>.json` でコマンド成否を確認する。smoke/start等の非同期処理は受付成功後に `jev status` とtraceで最終状態を確認する。
timeoutは結果不明として停止する。キュー投入成功を実行成功と扱わず、自動再送しない。残った `.processing` は再起動時にも再実行しない。

Jev以外のコンソールコマンド:

```powershell
tools/runtime/remote.ps1 -Action Command -Transport LastOrder -Command 'say test'
```

LastOrder側のallowlistに従う。返却は `QUEUED_NOT_VERIFIED` なので、ログや実状態で確認する。任意のコマンドを送る機能はあっても、allowlistの自動拡大はしない。
