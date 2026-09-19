---
name: build
description: JevControl PaperプラグインをJava 21でビルドし、unit test、配布JAR境界、一時診断ログ残存を検査する。必要なら隔離Paper実サーバーのsmokeも実行する。
---

# Build

リポジトリルートから `tools/runtime/build.ps1 -Clean -Smoke` を実行する。
成果物は `build/libs/jev-control-paper-0.2.0.jar`。通常の増分ビルドでは `-Clean` を省略できる。
毎回、ネットワーク不要のデプロイ模擬試験（ハッシュ不一致・重複拒否・旧JAR復元等）も実行する。
smokeは固定Paper 1.21.11 build 116をダウンロードしてSHA-256を検証し、`.runtime-harness/paper-smoke-*/` の隔離サーバーを起動する。既存fixtureのEULA確認を引き継ぐ。
実Jev APIは呼ばない。成功は `verification.json` のJARハッシュと対象成果物を照合する。
Java/身体実装を変えたらsmokeを再実行し、依存version変更時には共有サーバー互換性も確認する。
