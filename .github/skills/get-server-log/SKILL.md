---
name: get-server-log
description: 共有Paperテストサーバーのlatest.logとJevのJSONL実験traceを非破壊で回収し、起動・判断・入力・物理結果・停止状態を観測する。
---

# Evidence

```powershell
tools/runtime/remote.ps1 -Action Log -RunId investigation-1
tools/runtime/remote.ps1 -Action Traces -RunId investigation-1
```

`.runtime-harness/remote-<id>/` へ保存。raw logはそのまま保存し、出力要約はJevの行に限定する。
traceのsnapshot・input・result・terminalをrequest/run IDで対応付ける。実移動、health、tick数、停止理由で判定し、adapterの成功文字列だけを証拠にしない。`SMOKE_NO_MODEL` と実Jev評価は別。
一時観測を追加する場合はソースに `RUNTIME-DIAG` markerを付け、修正後に出力コードを全部除去してbuild検査・再実験を通す。共有サーバーの `latest.log` や他人のログを消さない。通常のtraceは専用ディレクトリへ残し、サーバーログを継続的に汚さない。
