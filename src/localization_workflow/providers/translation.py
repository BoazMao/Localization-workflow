"""Translation provider boundary and OpenAI Responses adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    segments: tuple[tuple[str, str], ...]
    source_language: str
    target_language: str
    wordbank: str
    instructions: str


class TranslationProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]: ...


class OpenAITranslationProvider:
    """Translate a contextual segment batch with one OpenAI Responses API call."""

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self.configure(api_key or "", model, base_url or "")

    def configure(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key.strip() or None
        self._model = model.strip()
        self._base_url = base_url.strip() or None

    @property
    def name(self) -> str:
        return "OpenAI"

    @property
    def model(self) -> str:
        return self._model

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured in .env.")
        wordbank = request.wordbank or "(No wordbank context provided)"
        segment_payload = [
            {"id": segment_id, "source": text} for segment_id, text in request.segments
        ]
        prompt = (
            f"Source language: {request.source_language}\n"
            f"Target language: {request.target_language}\n"
            "Wordbank and localization context (interpret naturally; use relevant guidance "
            f"without requiring exact source-text matches):\n{wordbank}\n\n"
            "Translate every segment below using the surrounding segments for context. "
            "Return only a JSON object in this exact shape: "
            '{"translations":[{"id":"original id","text":"translated text"}]}. '
            "Return exactly one non-empty translation for every supplied ID, preserve each ID "
            "exactly, and keep the original order.\n\n"
            f"Source segments:\n{json.dumps(segment_payload, ensure_ascii=False)}"
        )
        response = OpenAI(api_key=self._api_key, base_url=self._base_url).responses.create(
            model=self._model,
            instructions=request.instructions,
            input=prompt,
            store=False,
        )
        raw_result = response.output_text.strip()
        if not raw_result:
            raise RuntimeError("ChatGPT returned an empty translation.")
        start = raw_result.find("{")
        end = raw_result.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError("ChatGPT returned an invalid translation batch.")
        try:
            payload = json.loads(raw_result[start : end + 1])
        except json.JSONDecodeError as error:
            raise RuntimeError("ChatGPT returned malformed translation JSON.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("translations"), list):
            raise RuntimeError("ChatGPT returned an invalid translation batch structure.")
        translations: dict[str, str] = {}
        for item in payload["translations"]:
            if not isinstance(item, dict):
                raise RuntimeError("ChatGPT returned an invalid translation item.")
            segment_id = item.get("id")
            text = item.get("text")
            if not isinstance(segment_id, str) or not isinstance(text, str) or not text.strip():
                raise RuntimeError("ChatGPT returned an incomplete translation item.")
            if segment_id in translations:
                raise RuntimeError("ChatGPT returned a duplicate segment ID.")
            translations[segment_id] = text.strip()
        expected_ids = {segment_id for segment_id, _text in request.segments}
        if set(translations) != expected_ids:
            raise RuntimeError("ChatGPT did not return exactly one translation for every segment.")
        return translations
