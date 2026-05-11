"""LLM-output JSON extraction + schema validation.

Two functions for the "the model returned text but we want a parsed
dict" problem:

- :func:`extract_json_payload` strips markdown fences and prose
  surrounding the JSON body. Best-effort recovery for scorer responses
  that drift from "JSON only" prompt instructions.
- :func:`validate_llm_json` parses + validates against a JSON Schema
  loaded from disk. Returns ``(parsed, None)`` on success or
  ``(None, error_message)`` on parse / schema failure — never raises.

Extracted from ``utils.py`` in M4.E2.I2 (#550). No logic changes.
"""

from __future__ import annotations

import json
import re

_FENCED_JSON_RE: re.Pattern[str] = re.compile(r"```(?:json|JSON)?\s*\n(.*?)\n```", re.DOTALL)

# Markdown-bold-around-keys drift (#638). DeepSeek V3.2 intermittently emits
# JSON with keys wrapped in `**` despite the prompt forbidding markdown.
# Matches both observed shapes from 2026-05-11 pipeline.jsonl:
#   Variant A: **score_status**: "scored",     (bold around bare keyword)
#   Variant B: **"relevance_score": 1,          (bold prefix on quoted key, no closing)
# Anchored on a line start or JSON delimiter (`{`, `,`) so it cannot match
# inside a JSON string value where legitimate `**` may appear as prose.
_BOLD_KEY_RE: re.Pattern[str] = re.compile(
    r'(?P<anchor>^|[{,]\s*)\*\*"?(?P<key>\w+)"?(?:\*\*)?\s*:',
    re.MULTILINE,
)


def extract_json_payload(raw_output: str) -> str:
    """Pull the JSON payload out of an LLM response that may wrap it in
    markdown fences, prose, or both.

    Handles, in order:
    1. Whole response is a fenced block (```...```, possibly with a
       language tag like ```json). Strip the fences.
    2. Response contains a fenced ```json…``` block somewhere inside
       prose. Return the contents of the first such block.
    3. Response has prose before the JSON. Find the first '{' or '[',
       return the substring from there onward (the parser will reject
       trailing prose only if it's also non-JSON, which is fine — we
       optimize for prose-before-JSON, the observed failure mode).
    4. Otherwise return the input unchanged.

    This is best-effort recovery for scorer responses that drift from
    "JSON only" in the prompt despite explicit instructions; the parser
    that consumes the output still gates on `json.loads` + schema
    validation.
    """
    text = raw_output.strip()

    # Case 1: whole-response fenced block
    if text.startswith("```"):
        # Drop the opening fence line (which may carry a language tag
        # like "```json"), then strip a trailing fence if present.
        first_newline = text.find("\n")
        if first_newline != -1:
            inner = text[first_newline + 1 :]
            if inner.rstrip().endswith("```"):
                inner = inner.rstrip()[: -len("```")]
            return inner.strip()

    # Case 2: fenced block embedded in prose. Match the first ```json
    # or ``` (with optional lang tag) ... ``` block.
    fence_match = _FENCED_JSON_RE.search(text)
    if fence_match:
        return fence_match.group(1).strip()

    # Case 3: bare JSON preceded by prose. Anchor at the first { or [
    # that opens a JSON value.
    for opener in ("{", "["):
        idx = text.find(opener)
        if idx > 0:  # strictly prose-before; idx == 0 already parses
            text = text[idx:].strip()
            break

    # Defensive: strip markdown-bold around keys (#638). Anchored regex only
    # matches at line-start or after JSON delimiters, so legitimate `**`
    # inside string values is preserved.
    text = _BOLD_KEY_RE.sub(r'\g<anchor>"\g<key>":', text)
    return text


def validate_llm_json(raw_output: str, schema_path: str) -> tuple[dict | None, str | None]:
    import jsonschema

    text = extract_json_payload(raw_output)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"JSON parse: {e}"
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        jsonschema.validate(parsed, schema)
    except jsonschema.ValidationError as e:
        return None, f"Schema: {e.message}"
    return parsed, None
