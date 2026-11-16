"""Tests for app/answer.py, with a FAKE model (no OpenAI calls)."""

import json

from app.answer import (
    NOT_FOUND,
    answer_question,
    build_user_prompt,
    citation_label,
    parse_reply,
)


def chunk(kind, text, page_start, page_end=None, **metadata):
    page_end = page_end or page_start
    return {"id": "x", "text": text,
            "metadata": {"kind": kind, "page_start": page_start, "page_end": page_end, **metadata}}


INTEREST = chunk("clause", "5.1 Interest shall accrue monthly", 7, number="5.1")
PENAL = chunk("definition", '"Penal Charges" means 2% per month', 3, term="Penal Charges")


def fake_model(reply: dict):
    """A stand-in for complete_json that records what it was sent."""
    calls = []

    def complete(system, user):
        calls.append(user)
        return json.dumps(reply)

    complete.calls = calls
    return complete


# --- citation_label -----------------------------------------------------------

def test_labels():
    assert citation_label(INTEREST) == "Clause 5.1, page 7"
    assert citation_label(PENAL) == 'Definition of "Penal Charges", page 3'
    assert citation_label(chunk("section", "Annexure B\nFees", 49, 51, title="Annexure B")) == \
        "Annexure B, pages 49-51"
    assert citation_label(chunk("preamble", "LOAN AGREEMENT", 1)) == "Preamble, page 1"
    assert citation_label(chunk("page", "text", 4)) == "Page 4"


def test_label_shows_the_part_of_a_split_chunk():
    assert citation_label(chunk("clause", "...", 18, 19, number="7", part=4)) == "Clause 7 (part 4), pages 18-19"


def test_later_part_of_a_section_keeps_the_section_title():
    later_part = chunk("section", "The Bank may, in its sole discretion,", 17, 19,
                       title="Schedule 1/ Sanction Letter", part=2)
    assert citation_label(later_part) == "Schedule 1/ Sanction Letter (part 2), pages 17-19"


# --- build_user_prompt --------------------------------------------------------

def test_prompt_numbers_sources_from_one():
    prompt = build_user_prompt("What is the interest?", [INTEREST, PENAL])
    assert "[1] Clause 5.1, page 7\n5.1 Interest shall accrue monthly" in prompt
    assert '[2] Definition of "Penal Charges", page 3' in prompt
    assert prompt.endswith("Question: What is the interest?")


# --- parse_reply --------------------------------------------------------------

def test_parse_valid_reply():
    assert parse_reply('{"answer": "Monthly.", "sources": [1]}', 2) == ("Monthly.", [1])


def test_parse_not_found_reply():
    assert parse_reply('{"answer": null, "sources": []}', 2) == (None, [])


def test_answer_without_sources_counts_as_not_found():
    assert parse_reply('{"answer": "Monthly.", "sources": []}', 2) == (None, [])


def test_invented_and_repeated_sources_are_dropped():
    assert parse_reply('{"answer": "A", "sources": [3, 2, 2, 0, "1", true]}', 2) == ("A", [2])


def test_broken_json_counts_as_not_found():
    assert parse_reply("Sorry, I cannot help", 2) == (None, [])
    assert parse_reply("[1, 2]", 2) == (None, [])


# --- answer_question ----------------------------------------------------------

def test_answer_has_citations_built_from_metadata():
    model = fake_model({"answer": "It accrues monthly.", "sources": [1]})
    result = answer_question("When does interest accrue?", [INTEREST, PENAL], model)
    assert result["found"] is True
    assert result["answer"] == "It accrues monthly."
    assert [c["label"] for c in result["citations"]] == ["Clause 5.1, page 7"]
    assert result["citations"][0]["page_start"] == 7


def test_not_found_answer():
    model = fake_model({"answer": None, "sources": []})
    result = answer_question("Who is the CEO?", [INTEREST], model)
    assert result == {"found": False, "answer": NOT_FOUND, "citations": []}


def test_no_chunks_means_no_model_call():
    model = fake_model({"answer": "x", "sources": [1]})
    assert answer_question("anything", [], model)["found"] is False
    assert model.calls == []
