# Jev live functional probes — 2026-09-19

目的: Minecraft resident設計に必要な最小限のAPI疎通、英語/日本語理解、複合発話の分解を確認する。

分類: 少数のfunctional smoke probeであり、model性能benchmarkではない。

実行環境: このrepositoryの `tools/probes/jev_client.py`、`POST https://api.typesafe.ai/v1/systemone`。

解決model: 全probeで `jev-1.13.0`。

秘密情報: API keyは記録していない。

## Probe 1: survival action

現在の配置では `python .\tools\probes\jev_client.py` を実行する。

State概要:

- Minecraft day 1
- spawn付近、inventory空
- 6 hearts、hunger 16/20
- nightまで約8分
- oak、cave、plains
- goalはfirst night survivalとbasic tools

Questions:

- Choice: gather wood / explore cave / build shelter / gather food
- Noul: explorationより即時安全を優先すべきか

Observed:

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "next_action": {
      "choice": "gather_wood",
      "confidence": 0.97,
      "probabilities": {
        "build_shelter": 0.02,
        "explore_cave": 0.0,
        "gather_food": 0.0,
        "gather_wood": 0.98
      }
    },
    "danger": {"noul": 0.81}
  },
  "usage": {"input_tokens": 476, "output_tokens": 77}
}
```

Interpretation:

- Bounded action choiceは機能した。
- danger=0.81とgather_wood選択は矛盾ではないが、安全判断を行動Choiceと別にcodeでcomposeする必要がある。

## Probe 2: English social utterance

State:

```json
{
  "utterance": "Kai: How far along is the clock tower? I'll bring 64 glass tomorrow.",
  "resident": {
    "name": "Mira",
    "project": "clock_tower",
    "progress": 0.43,
    "missing_glass": 82
  },
  "speaker_relationship": {"familiarity": 0.72, "trust": 0.64},
  "nearby_danger": false
}
```

Observed key answers:

```json
{
  "intent": {
    "choice": "ask_project_status",
    "confidence": 0.97,
    "probabilities": {
      "greet": 0.0,
      "ask_project_status": 0.98,
      "offer_material": 0.02,
      "other": 0.0
    }
  },
  "asks_status": {"noul": 0.99},
  "offers_glass": {"noul": 0.97},
  "memory_kind": {
    "choice": "commitment",
    "confidence": 0.92,
    "probabilities": {
      "none": 0.02,
      "commitment": 0.94,
      "place_fact": 0.04,
      "gift_received": 0.0
    }
  },
  "response_act": {
    "choice": "report_and_thank",
    "confidence": 1.0
  },
  "safe_to_continue_project": {"noul": 0.56},
  "usage": {"input_tokens": 701, "output_tokens": 211}
}
```

Interpretation:

- primary intent Choiceだけではsecondary intentのofferを失う。
- 複合発話はindependent Noul fan-outで検出し、codeでcomposeする。
- memory kind、dialogue actのbounded decisionには使える。
- `danger=false`でも曖昧な安全質問は0.56。ImmediateSafetyControllerをJevへ任せない。

## Probe 3: Japanese utterance, Japanese questions

State中の発話:

```text
Kai: 時計塔、どこまでできた？ ガラスなら明日64個持ってくるよ。
```

Observed key answers:

```json
{
  "intent": {
    "choice": "ask_project_status",
    "confidence": 0.33,
    "probabilities": {
      "greet": 0.04,
      "offer_material": 0.11,
      "ask_project_status": 0.5,
      "other": 0.35
    }
  },
  "asks_status": {"noul": 0.46},
  "offers_glass": {"noul": 0.42},
  "memory_kind": {
    "choice": "none",
    "confidence": 0.64,
    "probabilities": {
      "place_fact": 0.2,
      "none": 0.73,
      "commitment": 0.03,
      "gift_received": 0.04
    }
  },
  "response_act": {
    "choice": "ask_clarification",
    "confidence": 0.79
  }
}
```

Interpretation:

- 進捗質問と約束の両方に失敗。
- 日本語questionsにすれば解決するという仮説も支持されない。

## Probe 4: Japanese utterance, English questions

State中の発話はProbe 3と同じ。questions/criteriaだけを英語化。

Observed:

```json
{
  "asks_status": {"noul": 0.18},
  "offers_glass": {"noul": 0.08},
  "language_understood": {
    "choice": "unclear",
    "confidence": 0.93,
    "probabilities": {
      "greeting": 0.0,
      "unrelated": 0.03,
      "project_and_offer": 0.02,
      "unclear": 0.95
    }
  },
  "usage": {"input_tokens": 441, "output_tokens": 92}
}
```

Interpretation:

- 問題はquestionsの言語だけではなく、日本語inputの理解にある。
- 少なくとも `jev-1.13.0` では、生の日本語chatをproduction decisionへ使わない。

## Probeから固定する設計判断

1. Jevへのstate/questions/criteriaは当面英語にする。
2. 日本語chatはdeterministic parserでsemantic frameへ変換し、そのframeを英語keyで渡す。
3. primary Choiceとmulti-label Noulを併用する。
4. safetyはcode-only。
5. 数値/座標/item idはcodeが抽出・検証する。
6. `jev-latest`ではなく、評価後にversionをpinする。
7. 本番前に100件以上のdomain-labelled setを作り、この4件を一般化しない。
