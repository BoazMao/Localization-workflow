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
            raise RuntimeError("The translation API key is not configured.")
        wordbank = request.wordbank or "(No wordbank context provided)"
        segment_payload = [
            {"line": index, "source": text}
            for index, (_segment_id, text) in enumerate(request.segments, start=1)
        ]
        prompt = (
            f"Source language: {request.source_language}\n"
            f"Target language: {request.target_language}\n"
            "Wordbank and localization context (interpret naturally; use relevant guidance "
            f"without requiring exact source-text matches):\n{wordbank}\n\n"
            "Translate every segment below using the surrounding segments for context. "
            "Return only a JSON object in this exact shape: "
            '{"translations":[{"line":1,"text":"translated text"}]}. '
            "Return exactly one non-empty translation for every supplied line number, copy each "
            "integer line number exactly, and keep the original order.\n\n"
            f"Source segments:\n{json.dumps(segment_payload, ensure_ascii=False)}"
        )
        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        if self._model.startswith("gpt-"):
            response = client.responses.create(
                model=self._model,
                instructions=request.instructions,
                input=prompt,
                reasoning={"effort": "low"},
                store=False,
            )
        else:
            response = client.responses.create(
                model=self._model,
                instructions=request.instructions,
                input=prompt,
                store=False,
            )
        return _parse_batch_result(response.output_text, request.segments)


def _parse_batch_result(raw_result: str, segments: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """Validate numbered model output and map it back to internal segment IDs."""
    raw_result = raw_result.strip()
    if not raw_result:
        raise RuntimeError("The model returned an empty translation.")
    start = raw_result.find("{")
    end = raw_result.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("The model returned an invalid translation batch.")
    try:
        payload = json.loads(raw_result[start : end + 1])
    except json.JSONDecodeError as error:
        raise RuntimeError("The model returned malformed translation JSON.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("translations"), list):
        raise RuntimeError("The model returned an invalid translation batch structure.")
    by_line: dict[int, str] = {}
    invalid_lines: list[str] = []
    for item in payload["translations"]:
        if not isinstance(item, dict):
            raise RuntimeError("The model returned an invalid translation item.")
        line_value = item.get("line")
        text = item.get("text")
        if isinstance(line_value, str) and line_value.isdecimal():
            line_value = int(line_value)
        if not isinstance(line_value, int):
            invalid_lines.append(str(line_value))
            continue
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"The model returned empty text for line {line_value}.")
        if line_value in by_line:
            raise RuntimeError(f"The model returned duplicate line number {line_value}.")
        by_line[line_value] = text.strip()
    expected_lines = set(range(1, len(segments) + 1))
    returned_lines = set(by_line)
    missing = sorted(expected_lines - returned_lines)
    unexpected = sorted(returned_lines - expected_lines)
    if missing or unexpected or invalid_lines:
        details = []
        if missing:
            details.append(f"missing lines: {_summarize_numbers(missing)}")
        if unexpected:
            details.append(f"unexpected lines: {_summarize_numbers(unexpected)}")
        if invalid_lines:
            details.append(f"invalid line values: {', '.join(invalid_lines[:10])}")
        raise RuntimeError("Incomplete translation batch (" + "; ".join(details) + ").")
    return {
        segment_id: by_line[index] for index, (segment_id, _source) in enumerate(segments, start=1)
    }


def _summarize_numbers(values: list[int]) -> str:
    shown = ", ".join(str(value) for value in values[:20])
    remaining = len(values) - 20
    return f"{shown} (+{remaining} more)" if remaining > 0 else shown
