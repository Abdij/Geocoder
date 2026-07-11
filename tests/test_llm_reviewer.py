from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.llm_reviewer import (
    build_reasoning_prompt,
    is_ollama_available,
    request_reasoning_note,
)

SAMPLE_CANDIDATES = [
    {
        "settlement": "Kaharey",
        "district": "Doolow",
        "region": "Gedo",
        "name_score": 93.8,
        "semantic_score": 88.0,
        "distance_km": 2.1,
        "approval_count": 3,
        "rejection_count": 0,
        "admin_conflict": False,
    },
    {
        "settlement": "Kaharey Health Center",
        "district": "Doolow",
        "region": "Gedo",
        "name_score": 71.4,
        "semantic_score": None,
        "distance_km": None,
        "approval_count": 0,
        "rejection_count": 1,
        "admin_conflict": False,
    },
]


def test_build_reasoning_prompt_includes_all_submitted_fields():
    prompt = build_reasoning_prompt(
        submitted_settlement="Kaharey Health Center",
        submitted_district="Doolow",
        submitted_region="Gedo",
        submitted_latitude=4.14,
        submitted_longitude=42.19,
        candidates=SAMPLE_CANDIDATES,
    )
    assert "Kaharey Health Center" in prompt
    assert "Doolow" in prompt
    assert "Gedo" in prompt
    assert "4.14" in prompt and "42.19" in prompt


def test_build_reasoning_prompt_includes_candidate_evidence():
    prompt = build_reasoning_prompt(
        submitted_settlement="Kaharey Health Center",
        submitted_district="Doolow",
        submitted_region="Gedo",
        submitted_latitude=None,
        submitted_longitude=None,
        candidates=SAMPLE_CANDIDATES,
    )
    assert "93.8%" in prompt
    assert "approved by analysts 3 time(s)" in prompt
    assert "rejected by analysts 1 time(s)" in prompt


def test_build_reasoning_prompt_states_advisory_only_and_no_invention_rule():
    prompt = build_reasoning_prompt(
        submitted_settlement="X",
        submitted_district=None,
        submitted_region=None,
        submitted_latitude=None,
        submitted_longitude=None,
        candidates=[],
    )
    assert "advisor only" in prompt.lower()
    assert "not automatically change" in prompt.lower()
    assert "no gazetteer candidates were found" in prompt.lower()


def test_build_reasoning_prompt_caps_word_limit_instruction():
    prompt = build_reasoning_prompt(
        submitted_settlement="X",
        submitted_district=None,
        submitted_region=None,
        submitted_latitude=None,
        submitted_longitude=None,
        candidates=[],
    )
    assert "40 words" in prompt


def test_request_reasoning_note_returns_none_when_ollama_unreachable():
    with patch("requests.post", side_effect=ConnectionError("no server")):
        result = request_reasoning_note(
            submitted_settlement="Kaharey",
            submitted_district="Doolow",
            submitted_region="Gedo",
            submitted_latitude=None,
            submitted_longitude=None,
            candidates=SAMPLE_CANDIDATES,
        )
    assert result is None


def test_request_reasoning_note_returns_trimmed_text_on_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Candidate 1 is most plausible given the close distance."}
    mock_response.raise_for_status.return_value = None
    with patch("requests.post", return_value=mock_response):
        result = request_reasoning_note(
            submitted_settlement="Kaharey",
            submitted_district="Doolow",
            submitted_region="Gedo",
            submitted_latitude=None,
            submitted_longitude=None,
            candidates=SAMPLE_CANDIDATES,
        )
    assert result == "Candidate 1 is most plausible given the close distance."


def test_request_reasoning_note_returns_none_on_empty_response():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": ""}
    mock_response.raise_for_status.return_value = None
    with patch("requests.post", return_value=mock_response):
        result = request_reasoning_note(
            submitted_settlement="Kaharey",
            submitted_district="Doolow",
            submitted_region="Gedo",
            submitted_latitude=None,
            submitted_longitude=None,
            candidates=SAMPLE_CANDIDATES,
        )
    assert result is None


def test_is_ollama_available_false_when_unreachable():
    with patch("requests.get", side_effect=ConnectionError("no server")):
        assert is_ollama_available(timeout=0.1) is False


def test_is_ollama_available_true_when_reachable():
    mock_response = MagicMock()
    mock_response.ok = True
    with patch("requests.get", return_value=mock_response):
        assert is_ollama_available(timeout=0.1) is True
