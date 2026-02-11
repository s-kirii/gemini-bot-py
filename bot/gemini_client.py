from __future__ import annotations

from typing import Any

import aiohttp


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._session = session

    async def generate_response(self, prompt: str, history: list[dict[str, Any]]) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": self._system_prompt}]},
            "contents": [*history, {"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }

        async with self._session.post(url, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Gemini API error {response.status}: {body}")
            data = await response.json()

        return _extract_text(data)


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not candidates:
        raise RuntimeError("Gemini API returned no candidates.")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    combined = "\n".join(text.strip() for text in texts if text and text.strip())
    if not combined:
        raise RuntimeError("Gemini API returned empty text.")

    return combined
