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

batch2の元の壁1run、その後の変更版assisted4診断を予約。結果は実行後に追記する。固定最終比較は同じ新JARで18runを行い、途中でprompt・候補・実行補助を変更しない。

## 検証・未達条件・証跡

初回診断4/4は旧artifactの結果。新artifactは再診断する。固定最終18件、各壁条件assisted2/3、壁後の迂回→元目標到達はまだ未実施/未達。UNKNOWN専用Paper試験の残件も保持する。実API異常が発生した場合はERRORとその証拠を残し、自動再試行しない。

再現例：

```powershell
python tools/runtime/p1b_acceptance.py --phase diagnostic --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --phase development --development-case original-wall --hypothesis <実行前に固定した仮説> --key-file <既存キー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --audit-directory <証拠ディレクトリ>
```

生trace、plan、receipt、JAR、consoleは `C:/github_folder/minecraft-ai-jev-embodied-control/.runtime-harness/` にローカル保存。公開するのはレポート、全結果の要約とハッシュ、source。APIキー、認証header、秘密ファイルを表示・保存・commitしない。ローカル検証・CI・小規模評価の結果をGate A通過や汎化性能へ読み替えない。
