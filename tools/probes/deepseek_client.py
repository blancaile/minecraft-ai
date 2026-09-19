"""Interactive multi-turn client for the DeepSeek Flash API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_deepseek_api_key(env_path: Path = ENV_PATH) -> str:
    """Read deepseek_api_key from the JSON-like .env format used by this project."""
    try:
        contents = env_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"DeepSeek key file was not found: {env_path}") from exc

    match = re.search(r'"deepseek_api_key"\s*:\s*"([^"]+)"', contents)
    if match is None or not match.group(1).strip():
        raise RuntimeError('Could not find a non-empty "deepseek_api_key" in .env')

    return match.group(1)


def chat(messages: list[dict[str, str]]) -> str:
    """Send the conversation history and return the assistant's next message."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_deepseek_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            result: dict[str, Any] = json.load(response)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"DeepSeek API returned HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the DeepSeek API: {exc.reason}") from exc

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek API returned an unexpected response") from exc
    if not isinstance(content, str):
        raise RuntimeError("DeepSeek API returned a non-text response")
    return content


def run_conversation() -> None:
    """Run an interactive conversation until the user exits or sends EOF."""
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Reply in the user's language.",
        }
    ]
    print(f"DeepSeek V4 Flash chat ({MODEL}). Type /exit to quit.")

    while True:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_message.lower() in {"/exit", "/quit"}:
            break
        if not user_message:
            continue

        messages.append({"role": "user", "content": user_message})
        try:
            answer = chat(messages)
        except RuntimeError:
            messages.pop()
            raise

        print(f"DeepSeek: {answer}")
        messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    try:
        run_conversation()
    except RuntimeError as exc:
        raise SystemExit(f"Error: {exc}") from exc
