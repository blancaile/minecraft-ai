# Issue #40：共有サーバーへの配置と実Jev検証

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。[隔離Paperの55試行](jev-control-p1b-live-evaluation-2026-09-20.md)は保持する。ユーザーの追加指示により、共有環境での配置・稼働・実検証までを完了条件とし、先のcloseを訂正してreopenした。

## 実行前の計画・受入条件

配置対象は隔離比較で9/9到達したsource `aebad6f`、JAR SHA-256 `d2efa94f3cb5def7a15cf6212614c1e27e4c3092989aedeff4a36a244c9afd02`。新しいplugin実装を混ぜない。既存JARをバックアップし、転送後の再取得ハッシュ、activation marker以降のJEV_READY、statusの稼働ハッシュを一致させる。

事前確認：共有 `/test_server/plugins` にJev JARは1個、LastOrderあり。旧稼働ハッシュ `ccd880f347345c2e81415fd77e11162a7f17df34512b62f4ce4433c6b6222c54`、botなし。常設Jevキーはconfigured、sealed RSA、config/private key各600・directory700。設定やキーを読み出さず `key-status` を使用する。

オンラインPhilia_Gray付近の検査済み3×7平坦レーンをrunごとに再選定する。地形は変更しない。`assisted`で南3block・東1.25block・西1.25block・北1.25blockの4到達runと、南5blockへ動作中の取消1run。後者は最初の判断が実行されてからstopする。各run60判断/120秒/240入力tick以下、全5run最大300判断/600秒/1,200入力tick。到達半径1、model jev-1.13.0。短い横方向目標は、安全検査済みレーン内で軸の選択と実移動を確認するためであり、長距離の横移動性能ではない。

受入条件は4到達、取消runのCANCELLED、全runが実Jev・assisted・配置JAR一致、候補→判断→固定終点→毎tick入力→実座標→停止の整合性、停止後の水平速度0.001未満・生存・despawn・最終botなし、認証設定保持。成功文字列だけで合格とせず、生traceを既存P1b verifierと共有用manifest検証で再計算する。失敗も保存し、再試行前に原因と追加計画を記録する。

共有での人工的な壁追加・地形改変は行わず、壁3条件の評価は隔離試験として区別する。共有環境の他pluginエラーはJevの結果と別に記録する。

## 結果・未達条件

現在は事前確認のみ。配置、activation、5run、後始末と監査は未実施。初回Preflightは専用worktreeにSFTP環境変数がなく失敗したが、既存の共有サーバー接続設定をメモリに読み、宛先が `/test_server/plugins` であることを確認して解決した。認証値は報告・証拠へ保存しない。

ローカル証拠は `C:/github_folder/minecraft-ai-jev-embodied-control/.runtime-harness/remote-p1b-shared-*/`。既存JARバックアップ、生trace、receipt、生ログはローカルのみ、公開報告には必要な指標・ハッシュと所在を記載する。
