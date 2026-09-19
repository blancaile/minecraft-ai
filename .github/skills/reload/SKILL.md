---
name: reload
description: 共有PaperテストサーバーへLastOrder経由でreloadを送り、今回のmarker以降に配布JARのSHA-256と一致するJev起動を確認する。
---

# Activation

Paperの通常の更新手段は再起動。共有サーバーで許可されたreload運用では以下を使う。

```powershell
tools/runtime/remote.ps1 -Action Reload
```

LastOrderで `say JEV_ACTIVATE_<id>` を送り、そのmarkerをログで確認してから `bukkit:reload confirm` を送る。marker以降に `JEV_READY` と配置JARのSHA-256が一致しない場合は失敗。他プラグインもreloadされるので、読取や配置準備だけを頼まれた場面では実行しない。
Jev自身のdisableは判断取消・入力解除・bot除去を行い、自動でrunを再開しない。`jev status` が `bot=none` であることも確認する。
reloadのタイムアウト時はログを取得して原因を確認し、繰り返し送信しない。
