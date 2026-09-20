# Issue #40：実JevによるP1b比較・開発記録

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。[固定条件・予算・batch事前計画](jev-control-p1b-plan-2026-09-20.md)。[初回実装と模擬試験](jev-control-p1b-report-2026-09-20.md)。

**結論：第2固定比較でassistedは各壁3/3、計9/9到達し、Issue #40の到達基準を達成した。directは6/9。** 第1固定比較の未達を保存し、履歴追加と迂回継続promptの2段階で実験を進めた。実Jevは全55run、1,679判断、1,690 API requests、7,086入力tick。到達42件・予算切れ13件、実API異常0件。全件の整合性・後始末を生traceから再検証した。開発を含む42/55を最終版の到達率とはしない。

## 目的・仮説・境界

Jevの近距離点選択＋コードの有限区間実行を、#39の直接入力方式と同じ条件・予算で比較する。方策の選択はJevに残し、コードは固定終点の入力変換・監視・解除のみを担う。候補の順位付け、目標へ戻る方向の自動選択、A*、自動迂回・ジャンプ、移動teleport、velocity直書きは加えない。

仮説は世界座標による選択と実行補助がyaw依存の失敗を減らす可能性。候補表現・操作粒度・補正を一緒に変えるため、補正単独の因果効果とはしない。先行OSSとの差は[P1aレポート](jev-control-p1a-experiment-report-2026-09-20.md)の固定source調査を引き継ぎ、今回はそのOSSを実行した順位比較ではない。

ユーザーは実Jev APIを継続的に許可し、実験検証サイクルの続行を指示した。AGENTSと実験スキルへ記録し、各runで再許可を求めない。共有サーバーの変更は行わない。

## 条件・方法

Paper 1.21.11 build116 / Java21 / jev-1.13.0。各run60判断・120秒・240入力tick、API timeout10秒、snapshot age200tick、初期座標 `(0.5,81,0.5)`、到達半径1。初回は診断8＋開発6＋固定最終18＝最大32run/1,920判断。未達後、理由と追加23run/1,380判断を事前記録し、累計上限55run/3,300判断で実施した。

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

第1比較の9件合計はdirectが395判断/398 API requests/1,580入力tick/199.788秒、assistedが381判断/382 API requests/1,751入力tick/211.637秒。API requestsには慣性で目標到達したときに取り消した未完了requestも含む。判断数の減少だけを仕事量・効率の改善とはしない。各runの終端距離、距離推移、latency p50/p95、snapshot age、停止理由、後始末、traceハッシュは[全試行JSON](jev-control-p1b-live-results-2026-09-20.json)に保存した。

## 第2campaign：迂回継続の指示を明確化

[追加事前計画](jev-control-p1b-plan-2026-09-20.md#追加campaignの事前計画)に従い、最大23件を追加する。Jevへのpromptに、目標方向が遮られたときは自分で選んだ通れる側への迂回を継続し、目標方向がCLEARになる前に直前の横移動を打ち消さないことを追加する。選択・再判断はJevに残り、コードの候補・履歴・制御則・guardは同一。

source `aebad6ffc843f3db74debd95972decfa77d015aa`、JAR `d2efa94f3cb5def7a15cf6212614c1e27e4c3092989aedeff4a36a244c9afd02`。初期yaw90のprobeは35判断・149入力tickで到達、生trace監査PASS（`.runtime-harness/p1b-development-239d86bcff33/`）。冒頭のE/W往復は4区間ほど残るが、その後Wを続けて選び、壁を回って目標へ戻った。1回の成功では安定性を主張しない。

この新artifactでもUNKNOWN試験を再実行し、0入力tick・実位置不変・水平速度0・despawnを確認（`.runtime-harness/p1b-smoke-3da45a08e2d8/`、PASS）。`build.ps1 -Smoke`もPASS。ログ `.runtime-harness/p1b-build-detour-prompt.log`、body証拠 `.runtime-harness/paper-smoke-1cb373b8d162/`。Java25件、remote7件、P0/P1a/P1b verifier各3/10/11件、身体22項目を確認した。

`aebad6f`の[CI](https://github.com/blancaile/minecraft-ai/actions/runs/35489453426)も成功した。Linux上のbuild/unit、身体smoke、既存direct異常停止、P1b模擬19件を含む。CIの模擬到達を実Jevの到達数へ加算しない。

4条件の再診断は各3判断・13入力tickで4/4到達（`.runtime-harness/p1b-development-7612b7071ecc/`）。第2固定比較は `.runtime-harness/p1b-final-6c125c824ee7/` に保存し、同一JAR・promptで18件を完了した。再監査の受入判定はPASS。

| 条件 | direct到達 | assisted到達 | assisted判断数（反復1/2/3） | assisted入力tick（反復1/2/3） |
|---|---:|---:|---|---|
| 元の壁 | 0/3 | 3/3 | 31 / 33 / 33 | 127 / 139 / 139 |
| 左右反転 | 3/3 | 3/3 | 29 / 29 / 29 | 119 / 119 / 119 |
| 初期yaw90 | 3/3 | 3/3 | 33 / 31 / 33 | 139 / 127 / 139 |

9件合計はdirectが382判断/385 API requests/1,528入力tick/196.439秒、assistedが281判断/284 API requests/1,167入力tick/151.542秒。失敗も含む総量であり、同じ成功回数あたりの費用ではない。assistedの各run所要時間は15.499〜18.150秒、最終距離0.4904〜0.9841、最大snapshot age17tick。全18件で介入時に身体が壁を通過していないこと、壁観測→新判断→入力→結果、終了後の静止・生存・despawnを確認した。

確認済み事実は、この改訂版が固定した3条件で9/9到達し、第1比較で残った予算切れが第2比較では発生しなかったこと。改善の原因候補は一般的な迂回継続指示だが、prompt選定に同じfixtureを使用し、モデル応答や実行時刻も異なる。単独要因の因果効果、将来の成功確率、未知地形での性能は確定していない。

未解決の一般化範囲：同じ3fixtureを使ってpromptを調整・再評価したため、未知の地形への汎化は未検証。段差、ジャンプ、流体内移動、複数体、長期計画、共有サーバー配置も今回の範囲外。受入達成後も、Jev単独の能力向上や実行補正だけの因果効果とは解釈しない。

## 検証・未達条件・証跡

| 受入項目 | 最終結果 |
|---|---|
| Jev選択と実行補助の分離 | schema・固定点・IDと毎物理tickのtraceで確認 |
| 距離/時間、衝突/期限/取消/UNKNOWN解除 | Java、実Paper模擬、最終JARのUNKNOWN再試験とCIで確認 |
| 4条件assisted診断とdirect保存 | 最終JARでも4/4、初回direct4件を保存 |
| 両方式9件ずつ、assisted各条件2/3以上 | 第2固定比較18件、assisted全条件3/3、監査PASS |
| 候補・判断・補正・新判断・実座標の追跡 | 全runの生traceを再検証。候補除外/順位付け/自動迂回なし |
| 全試行・距離推移・時間・latency・後始末・source等の保存 | 55実Jev件と失敗fixtureを保持、公開要約に指標・ハッシュ・ローカル所在を記載 |
| 報告 | 本文と[全55件のJSON](jev-control-p1b-live-results-2026-09-20.json)、Issue本文の結論・直接リンクを参照 |

第1固定比較の未達は取り消さない。第2固定比較は同じ到達基準を満たし、Issue #40の技術的な受入残件はない。共有配置・未知地形の汎化は未実施であり、今回の合格へ含めない。

同じ履歴版JARのUNKNOWN停止を実Paperで追加検証した。開いたフェンスゲートでspawnへの水流を止め、隣接する水が支持面への視線を遮るfixtureを使用。観測では `(1,80,0)` が `UNKNOWN/occluded`、水と開いたゲートのcollision boxは空。模擬policyのE選択をUNKNOWNで0入力tickのまま解除し、実位置不変・水平速度0・生存・despawnを確認した（`.runtime-harness/p1b-smoke-de421bb6e33c/`、PASS）。観測を人工的に書き換えていない。これにより初回報告のUNKNOWN実機確認の残件を解消した。

先行fixture `.runtime-harness/p1b-smoke-8236b98ec2a0/` はゲートなしで水を置いたため、入力開始前に水流が身体を移動させ、固定終点の範囲外ERRORとなった。decision/start/resultの監査と静止確認にも失敗したためHARNESS_ERRORを保存し、成功へ数えない。ゲート追加はこのfixture原因への修正であり、plugin・観測・guardの変更ではない。[両試行の公開要約](jev-control-p1b-unknown-results-2026-09-20.json)。

再現例：

```powershell
python tools/runtime/p1b_acceptance.py --phase diagnostic --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --phase development --development-case original-wall --hypothesis <実行前に固定した仮説> --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --phase final --diagnostic-directory <初回診断証拠> --rediagnostic-directory <同じ新artifactの4条件再診断証拠> --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --audit-directory <証拠ディレクトリ>
python tools/runtime/p1b_acceptance.py --phase smoke --smoke-case occluded-support --execute
python tools/runtime/p1b_report.py <証拠ディレクトリ1> <証拠ディレクトリ2> --output <公開要約JSON>
```

生trace、plan、receipt、JAR、consoleは `C:/github_folder/minecraft-ai-jev-embodied-control/.runtime-harness/` にローカル保存。公開するのはレポート、全結果の要約とハッシュ、source。APIキー、認証header、秘密ファイルを表示・保存・commitしない。ローカル検証・CI・小規模評価の結果をGate A通過や汎化性能へ読み替えない。
