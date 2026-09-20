# Jevの近距離選択と有限区間実行補助：P1b引継ぎ・検証報告

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。[実行前計画・再現コマンド](jev-control-p1b-plan-2026-09-20.md)。

## 現在の結論

補助付き制御、区間schema、trace監査、隔離Paperの試験runnerを実装し、最終JARの模擬実機試験18/18を通過した。実Jev診断・壁比較は実API実行の明示許可待ちで未実施、P1bの到達条件は未達扱い、Issueはopen。
この報告の模擬判断による到達はJevの性能評価ではない。共有サーバーへの配置・実API呼出しは行っていない。

## 背景・仮説・先行OSSとの違い

#38は実Jev4run/129cyclesと単純目標到達を確認したP0完了。#39は元の壁0/3、配置変更3/3、向き変更3/3でP1a未達。その結果・生証跡・比較artifactは変更しない。

今回の仮説は、Jevによる世界座標上の行き先選択とコードによる有限歩行を分けると、yaw依存の修正失敗や細かな判断を減らせる可能性がある、というもの。補助だけで迂回方向の選択が改善するとは仮定しない。
[P1a実験レポート](jev-control-p1a-experiment-report-2026-09-20.md)の先行OSS調査を引き継ぐ。今回はA*、経路追従、LLMによる計画、複数区間の自動実行を導入せず、Jevが選んだ単一区間だけを実行する。OSSとの実行比較や性能順位は未検証。候補表現・入力粒度・補正が同時に変わる方式比較なので、補正単独の因果効果とは言えない。

## 変更

- 全8方向・既知目標方向・WAITの候補を幾何生成。重複だけ統合し、目標から離れる候補も保持する。
- 0.8blockの固定終点、12tick/水平累積1block、許容差0.12、WAIT4tick、3tick連続0.01block未満の停滞を実装。
- 観測済みセルの身体幅・頭上・支持面を確認し、UNKNOWN・障害物・停滞・期限・取消・異常で解除。移動先の置換や自動迂回なし。
- Jev request→候補→固定区間→毎tick入力→実座標→終了理由をschemaとtraceで分離。取消の処理順を考慮して身体の物理更新回数を記録する。
- `start direct`/`start assisted`の共通60判断・120秒・240入力tick、診断8件、最終18件の固定順序・前提チェックを実装。従来の引数なし`start`は保存。
- loopback隔離fixtureで実位置z>=2.5のtickに壁を1回追加。追加時の実位置・区間・壁体積を記録。

## 検証・失敗の記録

`tools/runtime/build.ps1 -Smoke`でJava 24件、配置模擬7件、P0 verifier 3件、P1a verifier 10件、P1b verifier 9件、隔離Paperの既存身体smoke 22項目が成功。`python tools/runtime/p1b_acceptance.py --phase smoke --execute`で最終JARのP1b模擬試験18/18が成功。`python tools/runtime/paper_acceptance.py --mode faults --execute`でも既存directの異常時停止6/6が成功した。

- Javaの新規5テストで候補多様性、固定終点、衝突・距離・停滞・期限・WAIT、UNKNOWN、応答ID検証を確認。
- Pythonの新規9テストで終点置換、tick欠損/重複、未知フィールド、不正到達・予算、模擬判断の混入を拒否。
- 最初の隔離Paper試験 `.runtime-harness/p1b-smoke-8e56d1dd4b85/`：左右×yaw4条件で到達、WAITと壁停止・異常停止を確認したが、停滞と取消のテスト期待が不一致。全体はCRITERIA_NOT_MET。
- 減速amplifier5では12tickに達するだけで停滞しなかった。これは停止判定の失敗とは確認されていない。期限試験に分離し、amplifier6で停滞を検査する。
- inboxは1秒間隔のため、短い区間の取消命令が終了後に届いた。隔離試験の途中取消だけconsole入力へ変更した。
- 2回目 `.runtime-harness/p1b-smoke-5dbf5444367c/`：取消で実2物理tickに対してtraceが1tickと報告する不整合を検出。server callbackとconsole commandの実行順の違いを観測し、物理更新カウンタと実消費入力記録へ修正した。取消時の入力解除自体は確認済み。全体はCRITERIA_NOT_MET、成功へ書き換えない。

- 3回目 `.runtime-harness/p1b-smoke-c1b3dcae537b/` は15/15項目成功。取消は実2tickを正しく記録し、異常5種と取消後遅着は最初の1区間以外を適用しなかった。
- 追加試験 `.runtime-harness/p1b-smoke-b5e8e6594f51/`：両方式とも240tickで停止。静的壁では頭上の壁はOBSERVED、下部は遮蔽でUNKNOWNのため、停止理由がUNKNOWNになった。既知の身体交差を先に報告し、既知交差がない場合のUNKNOWN停止を維持するよう理由の優先順を修正。このbatchの全体判定はCRITERIA_NOT_METとして保存。
- 全失敗を含む[模擬試験の結果要約・証跡ハッシュ](jev-control-p1b-component-results-2026-09-20.json)。実Jev試行数は0。
- 最終 `.runtime-harness/p1b-smoke-a72258ac5739/` は18/18成功。左右×yaw4条件は各3判断/13入力tickで到達。WAIT4tick、期限12tick、停滞3tick、区間途中取消2tick、既知壁の入力前停止、動的介入後の再判断、両方式の240tick予算停止を確認。HTTP503・通信断・未知選択・timeout・stale・取消後遅着の6条件では、最初の1区間以外の適用なし。各run後に実速度<0.001・生存・despawnを確認、最終bot不在。
- 最終JAR SHA-256: `52dcfc836e727f25cb2d58eacdfb726d2bf27f29d9c046ec6745859add48408f`。最終body smoke: `.runtime-harness/paper-smoke-f4fb861d4944/`。buildログ: `.runtime-harness/p1b-build-final-guard.log`。
- directの `JevClient.payload` / `Observation.capture` / `ControlFrame` を基点commitと比較し、変更なしと確認。物理tickカウンタは区間traceだけへ追加し、directのpolicy snapshotを保持した。
- 既存directの最終fault試験: `.runtime-harness/paper-faults-ac2a1f6dbacc/`。5ケースERROR、取消後遅着はCANCELLED、全6ケースが最初のFORWARD 1回以外を適用せず停止した。`git diff --check`、新規文書の相対リンク、全18模擬runの後始末も確認した。

## 受入条件と未解決点

| Issue #40の条件 | 状態 |
|---|---|
| Jev選択と補助制御をschema/code/traceで区別 | 実装・模擬実機trace検証済み |
| 有限距離/時間、衝突/期限/取消/UNKNOWN解除をローカルとPaperで確認 | unitとPaper検証済み。UNKNOWNはunitおよび旧guard版の実機試験で確認。最終guard版では既知壁の停止理由を優先する |
| 実Jevの診断assisted 4/4、direct全結果 | 未実施 |
| 両方式各9件、assisted各壁2/3以上到達 | 未実施 |
| 多様性・選択・補正・壁後の新判断・到達の追跡 | 模擬判断で検証済み、実Jev未実施 |
| 全試行のメトリクス/後始末/provenance | 模擬試験を保存、実Jev未実施 |
| MarkdownレポートとIssue同期/readback | 本報告を作成。同期結果・実装commitはIssue本文を参照 |

観測された事実は、模擬判断での単純方向移動と失敗の再現。実Jevの選択・壁迂回の改善は未知であり、原因仮説としてのみ保持する。模擬判断では壁前に同じ方向を選び続ける試験を含むので、迂回成功とは報告しない。ローカルテスト・CI・Paper身体試験はGate A通過や実Jev診断の代替にならない。

## 証拠・再現・公開範囲

実装基点commit: `585853e21aea6d80ea175ab0487636259040829f`。引継ぎ専用worktree: `C:/github_folder/minecraft-ai-jev-embodied-control`。別worktreeのGate A未commit変更は触っていない。
実装sourceは本報告を追加したcommit。GitHub CIの新規P1bジョブも追加したが、このローカル報告時点で新commitのCI成功は未確認。
生JSONL、plan、receipt、console、隔離serverとJARは同worktreeの `.runtime-harness/p1b-*/` にローカル保存。秘密ファイル・キー・認証headerは保存/公開しない。GitHubにはコード・schema・計画・本報告を公開し、生traceはローカルのみ。

再現手順・予算・環境・方式順は[固定計画](jev-control-p1b-plan-2026-09-20.md)。実APIはruntime-experimentスキルの明示許可条件に従う。診断が不合格なら結果を報告し、壁評価へ進まない。
