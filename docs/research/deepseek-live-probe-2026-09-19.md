# DeepSeek live probe (2026-09-19)

目的: Minecraft Resident の日本語解析・表現生成候補として、現在の DeepSeek API の最小挙動と失敗条件を確認する。これは精度評価ではなく疎通 smoke test である。

## 環境

- endpoint: `POST https://api.deepseek.com/chat/completions`
- model alias: `deepseek-flash`
- 実行日: 2026-09-19 (Asia/Tokyo)
- 秘密鍵と完全なHTTPログは保存しない

公式 Change Log 上、`deepseek-flash` は 2026-09-10 リリースの DeepSeek-V4.1-Flash を指す。alias は将来更新されうるため、本番ログでは model、`system_fingerprint`、schema/prompt version を記録する。

## Probe 1: 既存クライアント相当

`tools/probes/deepseek_client.py` と同等に、messages と model を渡し、日本語発話から intent、対象、数量、期限を JSON 化するよう依頼した。

結果: HTTP request は成功したが `message.content` が空だった。

含意:

- HTTP 2xx を推論成功とみなせない。
- `content == ""`、JSON parse failure、finish reason を別々に計測する。
- 空応答時は bounded retry の後に rule/template fallback を使う。

## Probe 2: JSON mode、thinking disabled

次を明示して再試行した。

- `thinking: {"type": "disabled"}`
- `response_format: {"type": "json_object"}`
- prompt 本文で JSON 出力を明記
- `max_tokens: 512`

入力の趣旨:

> 「時計塔はどこまでできた？ ガラスなら明日64個持ってくるよ」から intent、project、offer、数量、期限を抽出し、返答する。

得られた構造の要約:

```json
{
  "intents": ["progress_report", "offer_item"],
  "project": "時計塔",
  "offered_item": "ガラス",
  "offered_count": 64,
  "due_reference": "明日",
  "reply_ja": "時計塔の進捗と不足数に触れ、申し出へ礼を述べる返答"
}
```

- finish reason: `stop`
- usage: prompt 119、completion 73、total 192 tokens

## 批判的評価

良かった点:

- 日本語の project、item、数量、期限、申し出を抽出できた。
- JSON として parse 可能だった。
- 文脈に沿う日本語返答を作れた。

問題点:

- ユーザーは進捗を**質問**したのに、`progress_report` と命名した。schema enum と定義が曖昧なら semantic drift が起きる。
- 入力の「64個」を返答では「64枚」に変更した。自然な助数詞への補正でも、世界の事実を無断で変えているため resident では不合格。
- 返答中の進捗率や不足数は prompt で与えた事実に依存する。モデル自身を world truth の出典にできない。
- 1件だけなので、accuracy、再現性、option/order sensitivity の証拠にはならない。

## 実装への反映

1. `ASK_PROJECT_STATUS` のような閉じた enum と日本語定義を schema に入れる。
2. 入力の item/count/unit/deadline は fact ID で参照させる。
3. 出力を `utterance`, `used_fact_ids`, `claims[]` に分ける。
4. 数量、単位、固有名、場所、期限、進捗を deterministic validator で照合する。
5. invalid/empty/timeout/unsupported claim は発話を破棄し、template fallback にする。
6. 少なくとも300件の Gate B dataset で Rule/Jev/DeepSeek/Hybrid を比較する。

## 参照

- [DeepSeek API: JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [DeepSeek API: Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek API: Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek API: Change Log](https://api-docs.deepseek.com/updates/)

公式ドキュメントも JSON mode で空 content が返る場合があること、tool arguments が無効な JSON や schema 外の値になりうることを注意点としている。したがって、実行前 validation は probe 固有の対策ではなく、API 契約上も必要である。
