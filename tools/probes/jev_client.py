"""Minimal Jev client for choosing the next Minecraft pseudo-player action."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.typesafe.ai/v1/systemone"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_jev_api_key(env_path: Path = ENV_PATH) -> str:
    """Read the key from the JSON-like format documented in README.md."""
    try:
        contents = env_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Jev key file was not found: {env_path}") from exc

    match = re.search(r'"jev_api_key"\s*:\s*"([^"]+)"', contents)
    if match is None:
        raise RuntimeError('Could not find "jev_api_key" in .env')

    return match.group(1)


def ask_jev(state: str, questions: dict[str, Any]) -> dict[str, Any]:
    """Send one structured decision request to Jev and return its JSON response."""
    payload = {
        "model": "jev-latest",
        "state": state,
        "questions": questions,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_jev_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Jev API returned HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the Jev API: {exc.reason}") from exc


def choose_next_action() -> dict[str, Any]:
    """Ask Jev what the pseudo-player should do next in its current situation."""
    state = (
        "Minecraft day 1. The pseudo-player is near its spawn point with an empty "
        "inventory. It has 6 hearts, hunger is 16/20, and night is approaching "
        "in about 8 minutes. Nearby: oak trees, a small cave entrance, and open "
        "plains. Goal: survive the first night and prepare basic tools."
    )
    questions = {
        "next_action": {
            "type": "choice",
            "instructions": "Which single action should the Minecraft pseudo-player take next?",
            "criteria": {
                "gather_wood": "Collect oak logs to make basic tools and a crafting table.",
                "explore_cave": "Enter the nearby cave to look for stone and resources.",
                "build_shelter": "Build a simple shelter immediately before night.",
                "gather_food": "Search the plains for food before doing anything else.",
            },
        },
        "danger": {
            "type": "noul",
            "instructions": (
                "Is the current situation urgent enough that the player should "
                "prioritize immediate safety over exploration?"
            ),
        },
    }
    return ask_jev(state, questions)


if __name__ == "__main__":
    print(json.dumps(choose_next_action(), ensure_ascii=False, indent=2))
