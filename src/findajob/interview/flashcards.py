"""Flashcard deck builder: LLM JSON → .apkg (Anki) + .csv (Quizlet) + .json (UI).

Uses deterministic IDs so re-imports into Anki update existing cards rather
than creating duplicates (preserving spaced-repetition scheduling state).
"""

import csv
import hashlib
import json
import os
import re
from typing import TypedDict

import genanki


class Flashcard(TypedDict):
    front: str
    back: str
    tags: list[str]


VALID_TAGS = frozenset({"behavioral", "technical", "company", "role", "elevator", "closing"})

_MODEL_ID = 1607392319  # stable constant — changing this resets all card templates in Anki


def _stable_deck_id(company: str, title: str) -> int:
    """Deterministic deck ID from (company, title) so Anki treats re-imports
    as updates to the same deck, preserving review history."""
    h = hashlib.sha256(f"findajob:flashcards:{company}:{title}".encode()).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _card_guid(company: str, title: str, index: int) -> str:
    """Stable per-card GUID so Anki deduplicates across re-imports."""
    return genanki.guid_for(f"findajob:{company}:{title}:{index}")


def parse_flashcards_json(raw: str) -> list[Flashcard]:
    """Parse LLM output into validated flashcard list.

    Handles common LLM failure modes: markdown fences, trailing prose,
    BOM, leading/trailing whitespace.
    """
    text = raw.strip()
    if text.startswith("﻿"):
        text = text[1:]
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in LLM output")
    text = text[start : end + 1]

    cards: list[dict] = json.loads(text)
    if not isinstance(cards, list):
        raise ValueError(f"Expected JSON array, got {type(cards).__name__}")

    validated: list[Flashcard] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        front = str(card.get("front", "")).strip()
        back = str(card.get("back", "")).strip()
        if not front or not back:
            continue
        raw_tags = card.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        tags = [t for t in raw_tags if isinstance(t, str) and t in VALID_TAGS]
        if not tags:
            tags = ["behavioral"]
        validated.append(Flashcard(front=front, back=back, tags=tags))

    if not validated:
        raise ValueError("No valid flashcards after parsing")
    return validated


def build_apkg(cards: list[Flashcard], company: str, title: str, output_path: str) -> None:
    """Write an Anki .apkg package file."""
    model = genanki.Model(
        _MODEL_ID,
        "findajob Interview Flashcard",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": "{{Front}}",
                "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
            }
        ],
    )
    deck_id = _stable_deck_id(company, title)
    deck = genanki.Deck(deck_id, f"Interview: {company} — {title}")

    for i, card in enumerate(cards):
        note = genanki.Note(
            model=model,
            fields=[card["front"], card["back"]],
            tags=card["tags"],
            guid=_card_guid(company, title, i),
        )
        deck.add_note(note)

    genanki.Package(deck).write_to_file(output_path)


def write_csv(cards: list[Flashcard], output_path: str) -> None:
    """Write a Quizlet-importable CSV (front, back, tags)."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["front", "back", "tags"])
        for card in cards:
            writer.writerow([card["front"], card["back"], ";".join(card["tags"])])


def write_json(cards: list[Flashcard], output_path: str) -> None:
    """Write the validated flashcard JSON for the web UI to consume."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)


def build_all(raw_json: str, company: str, title: str, output_dir: str, base_name: str) -> dict[str, str]:
    """Parse LLM output and write all three output files.

    Returns dict of {format: absolute_path} for files written.
    Raises ValueError if JSON parsing fails entirely.
    """
    cards = parse_flashcards_json(raw_json)

    apkg_path = os.path.join(output_dir, f"{base_name}.apkg")
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    json_path = os.path.join(output_dir, f"{base_name}.json")

    build_apkg(cards, company, title, apkg_path)
    write_csv(cards, csv_path)
    write_json(cards, json_path)

    return {"apkg": apkg_path, "csv": csv_path, "json": json_path}
