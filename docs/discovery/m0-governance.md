# M0 — Gate A Discovery governance

状態: Active after this document is merged into `main`.

Baseline source commit: `8501f453b938517d91ff1edd4fcd78a307c8b9ef`

Baseline merge commit: `0922333743dd12c35f0fb010f5a3cc0548dac5e6`

## 1. Purpose

M0の目的はResidentを実装することではない。Minecraft body候補を第三者部品として査定し、Gate Aで何をどう証明できるかを確定することである。

`mc_aiplayer`は採用予定の上流ではなく候補の一つである。M0の正常なDecisionには次を含む。

- `EXTEND`
- `PERMANENT_FORK`
- `SELECTIVE_PORT`
- `REJECT`
- `DEFER`。再評価期限、条件、必要な外部変化を必須とする

## 2. Management boundary

GitHub Milestone、Issues、PR、ADR、Gate契約、Evidence索引はすべて`blancaile/minecraft-ai`で管理する。

第三者repositoryにはM0のIssueやPRを作らない。上流を実行する場合は監査済みの固定SHAを使用し、結果に上流SHAと本repositoryのSHAを記録する。

M0で作るMilestoneは`M0 — Gate A Discovery`の一つだけとする。M1はGA-005の結果として初めて作る。

## 3. Ordered issues

| Order | Issue | Result |
|---:|---|---|
| 1 | GA-001 Define Gate A Intent Contract | 何を証明したいか、対象・対象外、許容しないfailureを定義する。最終Acceptance Contractではない |
| 2 | GA-000 Upstream provenance / execution safety audit | 固定候補を安全に実行できるか確認する |
| 3 | GA-002 Reproduce pinned upstream baseline | 上流を変更せず、既存test/evidenceを再現する |
| 4 | GA-003 Body capability / gap / coupling matrix | 候補を相対比較し、独立検証可能性と結合コストを明らかにする |
| 5 | GA-004 ADR: body strategy | EXTEND / FORK / SELECTIVE_PORT / REJECT / DEFERを決定する |
| 6 | GA-005 Freeze Gate A Contract v1 and generate M1 backlog | 実測に基づき測定方法・threshold・M1だけを確定する |

GA-001がIntentを固定した後、GA-000、GA-002、GA-003を順番に実行する。後続Issueの本文は先行IssueのFindingに反していれば更新する。

## 4. Issue Definition of Done

M0 Issueは`1 Issue = 1 evidence-bearing unit of work`とする。repository変更がある場合は原則として一つのPRへ対応させるが、実行とEvidenceだけで完了するIssueに無理なPRを要求しない。

Closeには次が必要である。

- Acceptance Criteriaが判定済み
- Evidenceの場所、commit、実行条件が記録済み
- failure、timeout、partial resultが隠されていない
- `Decision / Finding`がplaceholderから実結果へ更新済み
- 次のIssueやADRへの影響が明記済み

## 5. Evidence independence

上流Harnessは診断と既存能力の理解に利用できるが、採否判断の唯一の審判にはしない。GA-003では各能力を次で分類する。

- `UPSTREAM_SELF_TEST`
- `OUR_BLACK_BOX`
- `BOTH`
- `NONE`

独立Acceptance HarnessはM0で先回りして完成させない。GA-002で観測・起動・artifact境界を確認し、`OUR_BLACK_BOX_VERIFY = possible / difficult / impossible`をGA-003に記録する。必要な最小HarnessはGA-005後のM1候補とする。

## 6. Candidate matrix requirements

GA-003は少なくとも次の列を持つ。

```text
Requirement
Candidate
Existing implementation
Existing upstream test
Existing upstream evidence
Our black-box verification
Evidence independence
Status: REUSE / EXTEND / MISSING / BLOCKED / UNVERIFIED
Coupling cost
Portability
Expected modification area
Operational risk
Required work
```

`mc_aiplayer`を中心に査定するが、アンカリングを避けるためMineflayerとCarpet fake playerを軽量な比較対象に含める。本格的な導入や同等量のprobeは要求しない。

## 7. Discovery code

production architectureへの恒久変更はM0で行わない。必要なadapter、instrumentation、task submission probeは`spike/ga-*` branchで許可する。

spikeコードは使い捨て、またはM1の正式Issueで再実装する。Discovery中に暗黙にproduction codeへ昇格させない。

## 8. Explicit non-goals

M0では次を実装しない。

- Jev runtime integration
- DeepSeek production integration
- Resident memory
- relationship system
- conversation system
- building grammar / landmark project
- new pathfinder
- new fake-player implementation
- Gate A gapのproduction修正

GA-003で必要性が判明しても、M1候補へ送る。

## 9. AI work assignment

AI coding agentへ渡す範囲は、一つのGA Issue本文、関連ファイル、Acceptance Criteriaに限定する。

`M0全部`、`Gate Aを完成`、`Residentを作る`という単位では依頼しない。後続Issueを先取りせず、先行IssueのEvidenceとFindingを確認してから次へ進む。

## 10. M0 completion

次をすべて満たした時点でM0を完了する。

1. pinned body候補を安全に再現した
2. Gate A候補能力を実測した
3. 全Gate A requirementをgap/coupling matrixで分類した
4. body戦略を5択から決定した
5. 採用条件、撤退条件、DEFER時の再評価条件を記録した
6. Gate A Contract v1を実測に基づいてfreezeした
7. M1 backlogを根拠付きで生成した

Resident production codeが一行も増えていなくても、以上を満たせばM0は成功である。
