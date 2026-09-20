# Issue #40：実JevによるP1b比較・開発記録

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。[固定条件・予算・batch事前計画](jev-control-p1b-plan-2026-09-20.md)。[初回実装と模擬試験](jev-control-p1b-report-2026-09-20.md)。

## 目的・仮説・境界

Jevの近距離点選択＋コードの有限区間実行を、#39の直接入力方式と同じ条件・予算で比較する。方策の選択はJevに残し、コードは固定終点の入力変換・監視・解除のみを担う。候補の順位付け、目標へ戻る方向の自動選択、A*、自動迂回・ジャンプ、移動teleport、velocity直書きは加えない。

仮説は世界座標による選択と実行補助がyaw依存の失敗を減らす可能性。候補表現・操作粒度・補正を一緒に変えるため、補正単独の因果効果とはしない。先行OSSとの差は[P1aレポート](jev-control-p1a-experiment-report-2026-09-20.md)の固定source調査を引き継ぎ、今回はそのOSSを実行した順位比較ではない。

ユーザーは実Jev APIを継続的に許可し、実験検証サイクルの続行を指示した。AGENTSと実験スキルへ記録し、各runで再許可を求めない。共有サーバーの変更は行わない。

## 条件・方法

Paper 1.21.11 build116 / Java21 / jev-1.13.0。各run60判断・120秒・240入力tick、API timeout10秒、snapshot age200tick、初期座標 `(0.5,81,0.5)`、到達半径1。診断8＋開発6＋固定最終18＝最大32run/1,920判断。

壁は初めて実位置z>=2.5となったserver tickで追加。介入位置・tick・区間IDを記録し、既に通過した壁は有効に数えない。生traceのrequest→候補→選択→入力→結果、実座標、区間上限、停止後の速度とdespawnを監査する。実行済み試行を消して再試行で置き換えない。

## 初回診断：assisted4/4、direct3/4

実装source `c1e8c8239638701e6908812586595cf2d8c11bba`。
JAR `52dcfc836e727f25cb2d58eacdfb726d2bf27f29d9c046ec6745859add48408f`。
証拠 `.runtime-harness/p1b-diagnostic-22a4c97ef819/`、生trace監査PASS。

| 条件 | 方式 | 到達 | 判断数 | 入力tick | 終端距離 | 秒 |
|---|---|---:|---:|---:|---:|---:|
| 西、yaw0 | direct | 失敗 | 60 | 240 | 47.386 | 31.25 |
| 西、yaw0 | assisted | 成功 | 3 | 13 | 0.869 | 2.00 |
| 西、yaw90 | assisted | 成功 | 3 | 13 | 0.866 | 1.95 |
| 西、yaw90 | direct | 成功 | 3 | 12 | 0.659 | 2.05 |
| 東、yaw0 | direct | 成功 | 3 | 12 | 0.659 | 2.05 |
| 東、yaw0 | assisted | 成功 | 3 | 13 | 0.869 | 1.95 |
| 東、yaw90 | assisted | 成功 | 3 | 13 | 0.869 | 2.05 |
| 東、yaw90 | direct | 成功 | 3 | 12 | 0.659 | 1.90 |

確認済み事実：失敗したdirectはSTRAFE_LEFT56回、STRAFE_RIGHT4回を選択し、東の `(44.886,81,0.5)` で終了した。assistedは同じ西目標にWを3回選んだ。これは一組の診断であり、Jev一般の方向理解の保証ではない。

## 開発batch1：元の壁で往復、未到達

同じJAR、元の壁1run。証拠 `.runtime-harness/p1b-development-b8fb87fb9317/`。
47判断・240tickでBUDGET_EXCEEDED。44区間ENDPOINT_REACHED、2区間OBSERVED_OBSTACLE、最後は残り2tickによる期限停止。壁前でSを停止後、E/W往復が続き、終了位置は約 `(0.438,81,3.488)`。

観測・入力実行は破綻せず、Jev選択が目標復帰に結び付いていない。候補E/WはCLEAR、SとGOAL_DIRECTIONはOBSERVED_OBSTACLEとして残っていた。停滞の事実は確認できるが、記憶不足、prompt、モデル能力のどれが主因かはこの結果だけでは断定しない。

## 開発batch2：直近4区間の実結果を追加

実行前の仮説：一つ前だけではなく、直近4区間の実結果と、失敗した往復を避けるという一般的な指示を渡すことで、Jevが迂回を継続する判断を選べるかもしれない。
`jev-assisted-v2`に実際のsegment_resultの直近4件をそのまま追加し、入力と出力でdeep copyする。ルート推定、反転検出ラベル、推奨方向、候補除外は追加しない。Python監査で履歴が生traceの直近4件と一致することを検査する。

source `58becc4`、JAR `0ad2be7a60fdb2d93cbf820cb924dcb06253d15dd575b3370496faad362e53ac`。
元の壁1runは53判断・239入力tickで到達した（`.runtime-harness/p1b-development-353d5477b175/`）。壁前の往復はなお残り、約30判断目から東へ迂回して目標に戻った。上限に近い1回の成功であり、履歴追加による安定した改善や原因の確定とはしない。

変更版assistedの4診断はすべて3判断・13入力tickで到達した（`.runtime-harness/p1b-development-ddd2b14b0390/`）。両batchとも生trace監査PASS。初回direct4結果を保持し、新artifactの再診断として区別する。開発枠6件は使い切った。

固定最終比較は同じ新JARで18runを行い、途中でprompt・候補・実行補助を変更しない。証拠ディレクトリは `.runtime-harness/p1b-final-4e2aa02c7ae9/`。

## 第1固定比較：未達

18件を完了し、生trace・artifact・条件・後始末の整合性検査を通過した。到達基準の判定は `CRITERIA_NOT_MET`（auditの `passed=false` は受入未達）。全18件で壁介入後の観測→新判断→入力→結果を追跡できた。

| 壁条件 | direct到達 | assisted到達 | assisted受入 |
|---|---:|---:|---|
| 元の壁 | 0/3 | 1/3 | 未達 |
| 左右反転 | 3/3 | 3/3 | 達成 |
| 初期yaw90 | 2/3 | 1/3 | 未達 |

どちらも計5/9到達。assisted失敗4件はすべて240入力tickを消費した。履歴を追加しても、壁前のE/W往復が残った。途中で壁を回り始めても目標到達前に予算が尽きる例もある。区間終点の実行成功と、方策の目標達成は異なる。小標本で方式の優劣やyawの独立した効果を断定しない。

## 第2campaign：迂回継続の指示を明確化

[追加事前計画](jev-control-p1b-plan-2026-09-20.md#追加campaignの事前計画)に従い、最大23件を追加する。Jevへのpromptに、目標方向が遮られたときは自分で選んだ通れる側への迂回を継続し、目標方向がCLEARになる前に直前の横移動を打ち消さないことを追加する。選択・再判断はJevに残り、コードの候補・履歴・制御則・guardは同一。仮説の検証はこれから行う。

## 検証・未達条件・証跡

初回診断と履歴版再診断はそれぞれ4/4。第1固定最終18件は完了、各壁条件assisted2/3は未達。第2campaignの実API評価は未実施。実API異常が発生した場合はERRORとその証拠を残し、自動再試行しない。

同じ履歴版JARのUNKNOWN停止を実Paperで追加検証した。開いたフェンスゲートでspawnへの水流を止め、隣接する水が支持面への視線を遮るfixtureを使用。観測では `(1,80,0)` が `UNKNOWN/occluded`、水と開いたゲートのcollision boxは空。模擬policyのE選択をUNKNOWNで0入力tickのまま解除し、実位置不変・水平速度0・生存・despawnを確認した（`.runtime-harness/p1b-smoke-de421bb6e33c/`、PASS）。観測を人工的に書き換えていない。これにより初回報告のUNKNOWN実機確認の残件を解消した。

先行fixture `.runtime-harness/p1b-smoke-8236b98ec2a0/` はゲートなしで水を置いたため、入力開始前に水流が身体を移動させ、固定終点の範囲外ERRORとなった。decision/start/resultの監査と静止確認にも失敗したためHARNESS_ERRORを保存し、成功へ数えない。ゲート追加はこのfixture原因への修正であり、plugin・観測・guardの変更ではない。[両試行の公開要約](jev-control-p1b-unknown-results-2026-09-20.json)。

再現例：

```powershell
python tools/runtime/p1b_acceptance.py --phase diagnostic --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --phase development --development-case original-wall --hypothesis <実行前に固定した仮説> --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --audit-directory <証拠ディレクトリ>
```

生trace、plan、receipt、JAR、consoleは `C:/github_folder/minecraft-ai-jev-embodied-control/.runtime-harness/` にローカル保存。公開するのはレポート、全結果の要約とハッシュ、source。APIキー、認証header、秘密ファイルを表示・保存・commitしない。ローカル検証・CI・小規模評価の結果をGate A通過や汎化性能へ読み替えない。
