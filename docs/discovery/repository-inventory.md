# Pre-M0 repository inventory

棚卸し日: 2026-09-19 (Asia/Tokyo)

対象: `blancaile/minecraft-ai`

目的: M0 — Gate A Discoveryを開始する前の監査境界を確立する。

## 結論

現在の成果物は、研究記録とAPI probeで構成されている。Resident本体、Minecraft body、Gate A harnessはまだ実装されていない。

API probeはproduction候補ではなく研究補助物として`tools/probes/`へ隔離する。既存の研究文書は削除せず、将来同じ調査を繰り返さないための記録として保存する。

## 分類

| 対象 | 分類 | 処置 |
|---|---|---|
| `.gitignore` | KEEP | `.env`、`__pycache__/`、Python bytecodeを追跡しない |
| `README.md` | KEEP / UPDATE | 現在フェーズとprobeの配置を反映する |
| `jev_client.py` | MOVE / EXPERIMENTAL | `tools/probes/jev_client.py`へ移動する |
| `deepseek_client.py` | MOVE / EXPERIMENTAL | `tools/probes/deepseek_client.py`へ移動する |
| `docs/research/resident-implementation-plan-v2.md` | KEEP / UPDATE | Architecture RFCとして保存する |
| `docs/research/jev-only-minecraft-resident-research.md` | KEEP | Jev-only feasibility researchとして保存する |
| `docs/research/jev-live-probes-2026-09-19.md` | KEEP | API実測記録として保存する |
| `docs/research/deepseek-live-probe-2026-09-19.md` | KEEP | API実測記録として保存する |
| `.env` | LOCAL ONLY | Git追跡対象外。秘密値は文書・evidenceへ含めない |
| `__pycache__/`, `*.py[cod]` | GENERATED | Git追跡対象外 |
| 削除対象 | NONE | 現時点で削除すべき成果物はない |

## Git状態の起点

棚卸し開始時点の既存HEADは`642f3ee`で、`main`、`develop`、`playground`が同じcommitを指していた。未確定状態は次のとおりだった。

- tracked modification: `README.md`
- untracked: `deepseek_client.py`, `docs/`
- tracked files: `.gitignore`, `README.md`, `jev_client.py`

この棚卸しを反映したbaseline commitを、M0 Discoveryの開始境界とする。

## Baselineに含めるもの

- 研究文書一式
- `tools/probes/`へ分離したJev/DeepSeek疎通確認クライアント
- probe移動後もリポジトリ直下の`.env`を参照する修正
- M0 Discovery準備段階であることを示すREADME
- 本棚卸し記録

## Baselineに含めないもの

- `.env`とAPI key
- Python cache
- `mc_aiplayer`のソース、binary、artifact
- Gate A harnessやResident production code
- GitHub Milestone / Issueの内容

## 次の境界

baseline確立後に、自分たちの`blancaile/minecraft-ai`へ唯一のMilestone `M0 — Gate A Discovery`とGA-000〜005を作る。

`mc_aiplayer`は固定SHAで査定する第三者部品候補であり、このbaseline時点では採用、fork、移植を決定しない。
