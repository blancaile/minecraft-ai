# minecraft-ai

Minecraft上で長期間生活する疑似プレイヤーを作る。
Jev-onlyを研究profileとして比較可能に保ちつつ、製品profileでは必要に応じて
DeepSeekを会話・open-set proposalへ利用する。身体・安全・権限・実行は決定論的コードが担う。
jevのapiキーは、.envに"jev_api_key": "value"という形で保存されている。

Resident本体の実装前調査である **M0 — Gate A Discovery** は完了した。
Gate A v1はfreezeしたが、Gate A自体はまだ通過していない。`mc_aiplayer`の採用判断は期限付き`DEFER`であり、
次は **M1 — Gate A Gap Closure** の独立black-box decision trancheから開始する。

## 調査・設計

- [M0 — Gate A Discovery governance](docs/discovery/m0-governance.md)
- [Pre-M0 repository inventory](docs/discovery/repository-inventory.md)
- [Gate A Intent Contract（NOT FINAL ACCEPTANCE CONTRACT）](docs/gates/gate-a-intent.md)
- [Gate A Contract v1.0](docs/gates/gate-a-v1.md)
- [`mc_aiplayer` provenance / execution-safety audit](docs/discovery/mc-aiplayer-supply-chain-audit.md)
- [Pinned `mc_aiplayer` baseline reproduction](docs/discovery/pinned-baseline-results.md)
- [Gate A body candidate matrix](docs/discovery/body-candidate-matrix.md)
- [ADR-0001: Minecraft body strategy](docs/adr/0001-body-strategy.md)
- [Gate A schema and runner interface](harness/gate_a/README.md)
- [Minecraft Resident 実装計画 v2（Architecture RFC）](docs/research/resident-implementation-plan-v2.md)
- [Jev-only Minecraft 疑似プレイヤー 調査・実現計画](docs/research/jev-only-minecraft-resident-research.md)
- [Jev live functional probes (2026-09-19)](docs/research/jev-live-probes-2026-09-19.md)
- [DeepSeek live functional probe (2026-09-19)](docs/research/deepseek-live-probe-2026-09-19.md)

## JEV API の疎通確認

Python 3.10 以上で、プロジェクト直下から実行する。

```powershell
python .\tools\probes\jev_client.py
```

`tools/probes/jev_client.py` はリポジトリ直下の `.env` から `jev_api_key` を読み、Jev の `systemone` API に
Minecraft の次の行動を問い合わせる。追加パッケージは不要。

## DeepSeek V4 Flash との対話

`.env` に Jev のキーと同じ形式で DeepSeek API キーを保存する。

```text
"jev_api_key": "..."
"deepseek_api_key": "..."
```

プロジェクト直下から次を実行すると、複数ターンの対話を開始できる。

```powershell
python .\tools\probes\deepseek_client.py
```

終了するには `/exit` または `/quit` を入力する。`tools/probes/deepseek_client.py` は
DeepSeek の OpenAI 互換 Chat Completions API に接続し、公式推奨の
`deepseek-flash`（現在の DeepSeek V4.1 Flash）を使用する。旧モデル名
`deepseek-v4-flash` は互換性のため一時的に受け付けられるが、現在は同じ
V4.1 Flash にルーティングされる。

- [DeepSeek API: Your First API Call](https://api-docs.deepseek.com/)
- [DeepSeek API: Change Log](https://api-docs.deepseek.com/updates/)
