# Issue #40 P1b 実装・実行前計画

対象：[Issue #40](https://github.com/blancaile/minecraft-ai/issues/40)。基点 `585853e21aea6d80ea175ab0487636259040829f`。
設計根拠は[承認済み方針](../research/jev-assisted-control-plan-2026-09-20.md)。
#38のP0完了、#39の元の壁0/3という未達判定と比較artifactを保持する。

2026-09-20追記：ユーザーが実Jev API使用の継続的許可と実験検証サイクルの続行を指示。実行ごとの許可確認は不要。初回診断はcommit `c1e8c82` / JAR `52dcfc836e727f25cb2d58eacdfb726d2bf27f29d9c046ec6745859add48408f`で下記8runを実施する。開発6run・最終18runは未使用。最大32run / 1,920判断の計画を維持する。

初回診断結果：assisted4/4、direct3/4、生trace監査PASS。開発batch1は同じJARで元の壁1runだけ（60判断/120秒/240tick）。仮説は「近距離点と観測上の通過可否を使い、壁後に新しいJev判断で迂回・復帰できる」。残り開発枠5runは、必要なら壁probe1件と変更後のassisted再診断4件に使う。変更後の4診断は開発枠に計上し、初回direct4結果を保存したまま、最終比較の両方式9件ずつは変更後の同一JARで行う。新方式の成功を旧JARへ流用しない。

開発batch1結果：元の壁は47判断/240tickで未到達。44区間が終点到達、2区間が既知障害物で停止、最後は残り予算による期限停止。壁前の東西往復をtraceで確認した。開発batch2は直近4区間の実結果を追加する `jev-assisted-v2` を元の壁1runで試す。promptには過去4区間を使って失敗した往復を避けることと、迂回では一時的に目標距離が増えうることだけを追加する。方向・経路・候補順位・除外はコードへ追加しない。記憶不足が原因と確定したわけではなく、この情報追加で選択が変わるかを検証する。変更後の診断4runと合わせて開発枠6runを使い切り、合計最大32runは維持する。実行前の各planに新JARハッシュを固定する。

## 仮説と制御境界

### 追加campaignの事前計画

初回最終比較 `.runtime-harness/p1b-final-4e2aa02c7ae9/` は、元の壁でassisted1/3、初期向き条件でも先頭2件が未到達となり、各条件2/3の基準を満たせないことが確定した。残りも固定条件で完了し、失敗batchを保存する。既存32runを開発扱いへ変更しない。

追加理由は、直近4区間の履歴だけでは壁前のE/W往復が続き、予算を消費するという新しい証拠。次の仮説は、Jevへの一般的な指示を「目標方向が遮られたら、通れる横方向を自分で選び、目標方向が通れるまで同じ側への迂回を継続する」と明確化すれば、この往復が減る可能性があること。コードの方策、候補、順位、区間長、観測、履歴長、共通予算は変更しない。特定の壁・座標・正解方向は渡さない。これはpromptを含む方式の改訂であり、実行補正単独の効果とはしない。

追加上限は23run/1,380判断（初期向き条件の開発probe1、変更後assisted4診断、固定最終18）。累計最大55run/3,300判断。最初の最終比較が終了してから変更し、build/Smoke後にsourceと新artifactを固定する。probe失敗時は再診断・最終へ進まず、結果と次の仮説を別途記録する。再診断は4/4を要求し、最終比較は両方式とも新JARで各9件、順番・壁・到達条件を維持する。模擬UNKNOWN確認は実Jev件数へ含めない。

Jevが世界座標の近距離点を選び、コードがその固定終点へのyaw・前進入力を補正することで、yaw依存の操作を選ぶ負担を減らせる可能性がある。方向選択や障害物迂回が改善するかは未検証。比較で候補表現・操作粒度・補正が同時に変わるため、補正だけの因果効果とは解釈しない。

- `jev start` は従来の直接操作。`jev start direct` / `jev start assisted` は開始時に方式と共通予算を固定する。途中切替なし。
- assisted候補は E, SE, S, SW, W, NW, N, NE の順で0.8block、GOAL_DIRECTIONは `min(0.8, 水平目標距離)`、WAIT。座標差が1e-9未満の重複だけ統合する。目標から離れる点、観測上の障害物・UNKNOWNがある点も提示し、順位付け・迂回方向の選択はしない。
- 選択点は観測時の絶対座標を保持。応答受理時の現在位置から1block超、垂直差0.1超ならERROR。近傍点を作り直して応答へ置換しない。
- 歩行区間は最大12tick、実行中の水平累積距離1block、到達許容差0.12block。WAITは4tick。残り共通tick予算が短ければそこで終了する。
- yawは `atan2(-dx,dz)`、前進入力は `min(1,2*終点水平距離)`。横入力・ジャンプは0。選択終点以外への操舵なし。
- 3tick連続で水平移動0.01block未満ならSTALLED。実衝突、観測した障害物、UNKNOWN、平坦な支持面の欠如、垂直変位、距離限界、期限、取消・死亡・異常で解除する。
- 各tickで新しく採取したOBSERVEDセルのみを検査する。幅0.6・高さ1.8の身体と平坦な全面支持を、現在地から短い先読み区間を10分割して検査。先読みは `min(終点までの距離, 0.25+水平速度*2.3)`。遮蔽・未列挙・未ロードはUNKNOWN。流体・部分支持・段差は今回の歩行補助では停止する。
- 入力解除後の慣性をvelocity代入で消さない。traceに解除時速度と後続観測を残し、実機で静止を確認する。

`AssistedControl.INSTRUCTIONS`を固定promptとして公開し、snapshotにも保存する。directのpromptと8入力は#39最終版を保持する。条件名・壁の正解経路・「どちらへ回るべきか」はpolicyへ渡さない。

## 証跡

[segment schema](../schemas/jev-segment-v1.schema.json)は `segment_start` / `segment_tick` / `segment_result` を定義する。
request ID、選ばれた候補、固定終点、区間ID、毎tickの入力・実座標、終了理由を結ぶ。directも比較時には毎tickの実状態を記録する。
区間終了後に移動先が変わるには新しいJev request/decisionが必要。模擬判断には `fault_fixture=true` が付き、実Jev評価として認めない。

壁介入は明示的な `-Djev.fixture.enabled=true` とloopback bindを要求する隔離fixture専用機能。最初に実座標z>=2.5となったserver tickに1回だけ置く。実座標、tick、request/segment ID、壁体積、身体前端z<4の有効性を記録する。sharedへの配置は範囲外。

## 事前固定した比較

Paper 1.21.11 build 116 / Java 21 / jev-1.13.0。開始 `(0.5,81,0.5)`、到達半径1。
各runは60判断・120秒・240入力tick、API timeout10秒、snapshot age200tick、観測半径3。WAITも入力tick予算に含む。API待ち時間は区間tickへ含めない。

診断は西目標 `(-2.5,81,0.5)` と東目標 `(3.5,81,0.5)`、各yaw 0/90。順番は west/0: direct→assisted、west/90: assisted→direct、east/0: direct→assisted、east/90: assisted→direct。計8run。assisted 4/4到達と全8件の証拠監査を壁比較への前提にする。

最終比較の目標は `(0.5,81,20.5)`。元の壁はblock `[-1,81,4]..[1,83,4]`、配置反転は `[-2,81,4]..[0,83,4]`、初期向き条件は元の壁・yaw90。他はyaw0。
反復1..3の各回に元の壁→配置反転→初期向きの順、各組は `(反復番号+条件index)%2` が1ならdirect→assisted、0ならassisted→direct。計18run、9組の開始方式はdirect5・assisted4で均衡化する。

診断8＋開発最大6＋最終18＝最大32run / 1,920判断。新artifactに変更した場合、診断の到達を引き継がない。runnerは診断・開発・最終を実装し、開発枠の配分は実行前の別batch計画で明記する。診断不合格・API異常を黙って再試行せず、壁比較への移行を止める。

各壁条件assisted 2/3以上の到達、両方式各9件と全runの壁観測→新判断→入力→結果が必要。#39の3cycles後介入とは同条件比較ではない。

## 再現手順

```powershell
tools/runtime/build.ps1 -Smoke
python tools/runtime/p1b_acceptance.py --phase smoke --execute
python tools/runtime/p1b_acceptance.py --phase diagnostic
# 実Jev APIはユーザーから継続的に許可済み:
python tools/runtime/p1b_acceptance.py --phase diagnostic --key-file <既存のキー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --audit-directory <診断証拠ディレクトリ>
python tools/runtime/p1b_acceptance.py --phase final --diagnostic-directory <診断証拠ディレクトリ> --key-file <既存のキー設定ファイル> --execute
python tools/runtime/p1b_acceptance.py --audit-directory <最終証拠ディレクトリ>
```

plan-onlyは秘密ファイルを読まない。各実行前にartifact/source/harnessと条件を新規証拠ディレクトリのplanへ保存する。成功・失敗の生trace、receipt、結果、JARをローカル `.runtime-harness/p1b-*/` に保持する。実API実行の結果は[報告書](jev-control-p1b-report-2026-09-20.md)へ追記する。
