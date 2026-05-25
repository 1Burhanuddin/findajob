"""Tests for findajob.interview.flashcards module.

Covers JSON parsing (including LLM junk), .apkg generation, CSV export,
and the build_all orchestrator.
"""

import csv
import json
import os
import zipfile

import pytest

from findajob.interview.flashcards import (
    build_all,
    build_apkg,
    parse_flashcards_json,
    write_csv,
    write_json,
)

CLEAN_JSON = json.dumps(
    [
        {
            "front": "What is your leadership style?",
            "back": "Collaborative; I led a 12-person cross-functional team.",
            "tags": ["behavioral"],
        },
        {
            "front": "Describe a scaling challenge.",
            "back": "Grew the validation lab from 4 to 40 servers in 6 months.",
            "tags": ["technical"],
        },
        {
            "front": "What does Acme Corp do?",
            "back": "Cloud infrastructure provider focused on AI workloads.",
            "tags": ["company"],
        },
    ]
)


class TestParseFlashcardsJson:
    def test_clean_json(self):
        cards = parse_flashcards_json(CLEAN_JSON)
        assert len(cards) == 3
        assert cards[0]["front"] == "What is your leadership style?"
        assert cards[0]["tags"] == ["behavioral"]

    def test_json_wrapped_in_fences(self):
        raw = f"Here are your flashcards:\n\n```json\n{CLEAN_JSON}\n```\n\nHope that helps!"
        cards = parse_flashcards_json(raw)
        assert len(cards) == 3

    def test_json_with_leading_prose(self):
        raw = f"I've created 3 flashcards for you:\n\n{CLEAN_JSON}"
        cards = parse_flashcards_json(raw)
        assert len(cards) == 3

    def test_json_with_bom(self):
        raw = f"﻿{CLEAN_JSON}"
        cards = parse_flashcards_json(raw)
        assert len(cards) == 3

    def test_invalid_tags_get_default(self):
        raw = json.dumps([{"front": "Q?", "back": "A.", "tags": ["nonsense", "invalid"]}])
        cards = parse_flashcards_json(raw)
        assert cards[0]["tags"] == ["behavioral"]

    def test_mixed_valid_invalid_tags(self):
        raw = json.dumps([{"front": "Q?", "back": "A.", "tags": ["technical", "bogus"]}])
        cards = parse_flashcards_json(raw)
        assert cards[0]["tags"] == ["technical"]

    def test_skips_cards_without_front(self):
        raw = json.dumps(
            [
                {"front": "", "back": "A.", "tags": ["behavioral"]},
                {"front": "Q?", "back": "A.", "tags": ["behavioral"]},
            ]
        )
        cards = parse_flashcards_json(raw)
        assert len(cards) == 1

    def test_skips_cards_without_back(self):
        raw = json.dumps(
            [
                {"front": "Q?", "back": "", "tags": ["behavioral"]},
                {"front": "Q2?", "back": "A2.", "tags": ["technical"]},
            ]
        )
        cards = parse_flashcards_json(raw)
        assert len(cards) == 1

    def test_no_array_raises(self):
        with pytest.raises(ValueError, match="No JSON array"):
            parse_flashcards_json("This is not JSON at all")

    def test_empty_array_raises(self):
        with pytest.raises(ValueError, match="No valid flashcards"):
            parse_flashcards_json("[]")

    def test_string_tag_coerced_to_list(self):
        raw = json.dumps([{"front": "Q?", "back": "A.", "tags": "technical"}])
        cards = parse_flashcards_json(raw)
        assert cards[0]["tags"] == ["technical"]


class TestBuildApkg:
    def test_creates_valid_apkg(self, tmp_path):
        cards = parse_flashcards_json(CLEAN_JSON)
        output = str(tmp_path / "deck.apkg")
        build_apkg(cards, "Acme Corp", "Engineer", output)
        assert os.path.isfile(output)
        assert os.path.getsize(output) > 0
        # .apkg is a zip containing an anki2 sqlite db
        assert zipfile.is_zipfile(output)

    def test_stable_deck_id_across_calls(self, tmp_path):
        cards = parse_flashcards_json(CLEAN_JSON)
        out1 = str(tmp_path / "deck1.apkg")
        out2 = str(tmp_path / "deck2.apkg")
        build_apkg(cards, "Acme", "Role", out1)
        build_apkg(cards, "Acme", "Role", out2)
        # Both files should be valid (deterministic IDs don't crash)
        assert zipfile.is_zipfile(out1)
        assert zipfile.is_zipfile(out2)


class TestWriteCsv:
    def test_creates_valid_csv(self, tmp_path):
        cards = parse_flashcards_json(CLEAN_JSON)
        output = str(tmp_path / "cards.csv")
        write_csv(cards, output)
        with open(output, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[0] == ["front", "back", "tags"]
        assert len(rows) == 4  # header + 3 cards
        assert "behavioral" in rows[1][2]


class TestWriteJson:
    def test_creates_valid_json(self, tmp_path):
        cards = parse_flashcards_json(CLEAN_JSON)
        output = str(tmp_path / "cards.json")
        write_json(cards, output)
        with open(output, encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded) == 3
        assert loaded[0]["front"] == cards[0]["front"]


class TestBuildAll:
    def test_writes_all_three_files(self, tmp_path):
        paths = build_all(
            raw_json=CLEAN_JSON,
            company="TestCo",
            title="SRE",
            output_dir=str(tmp_path),
            base_name="Test Flashcards - TestCo - SRE - 20260524-120000",
        )
        assert os.path.isfile(paths["apkg"])
        assert os.path.isfile(paths["csv"])
        assert os.path.isfile(paths["json"])
        assert "TestCo" in os.path.basename(paths["apkg"])

    def test_raises_on_invalid_json(self, tmp_path):
        with pytest.raises(ValueError):
            build_all(
                raw_json="not json",
                company="X",
                title="Y",
                output_dir=str(tmp_path),
                base_name="fail",
            )
