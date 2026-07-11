from __future__ import annotations

from typing import Any

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_MODEL = "qwen2.5"
OLLAMA_TIMEOUT_SECONDS = 8
MAX_NOTE_WORDS = 40


def is_ollama_available(timeout: float = 2.0) -> bool:
    try:
        import requests

        response = requests.get(OLLAMA_TAGS_URL, timeout=timeout)
        return response.ok
    except Exception:
        return False


def _format_candidate_evidence(candidates: list[dict[str, Any]]) -> str:
    lines = []
    for rank, candidate in enumerate(candidates, start=1):
        settlement = candidate.get("settlement", "?")
        district = candidate.get("district") or "unknown"
        region = candidate.get("region") or "unknown"
        name_score = candidate.get("name_score")

        header = f"{rank}. {settlement} (district: {district}, region: {region})"
        if isinstance(name_score, (int, float)):
            header += f" - name match {name_score:.1f}%"

        detail_bits = []
        semantic_score = candidate.get("semantic_score")
        if isinstance(semantic_score, (int, float)):
            detail_bits.append(f"semantic similarity {semantic_score:.1f}%")
        distance_km = candidate.get("distance_km")
        if isinstance(distance_km, (int, float)):
            detail_bits.append(f"{distance_km:.1f}km from submitted coordinate")
        approval_count = candidate.get("approval_count", 0)
        if approval_count:
            detail_bits.append(f"approved by analysts {approval_count} time(s) before")
        rejection_count = candidate.get("rejection_count", 0)
        if rejection_count:
            detail_bits.append(f"rejected by analysts {rejection_count} time(s) before")
        if candidate.get("admin_conflict"):
            detail_bits.append("district/region conflict with submitted record")

        if detail_bits:
            header += " - " + ", ".join(detail_bits)
        lines.append(header)
    return "\n".join(lines)


def build_reasoning_prompt(
    *,
    submitted_settlement: str,
    submitted_district: str | None,
    submitted_region: str | None,
    submitted_latitude: float | None,
    submitted_longitude: float | None,
    candidates: list[dict[str, Any]],
) -> str:
    """Build a structured, evidence-grounded prompt for the local reasoning model.

    Every fact the model is given is data the pipeline already computed -
    the prompt explicitly forbids inventing a settlement or coordinate not
    listed, and frames the response as advisory only.
    """
    coords = (
        f"{submitted_latitude}, {submitted_longitude}"
        if submitted_latitude is not None and submitted_longitude is not None
        else "not provided"
    )
    evidence = _format_candidate_evidence(candidates) if candidates else "No gazetteer candidates were found."

    return (
        "You are assisting a human analyst reviewing a humanitarian settlement-name match "
        "for Somalia. You are an advisor only: your answer will not automatically change any "
        "decision, confidence score, or selected candidate. Never propose a settlement name or "
        "coordinate that is not explicitly listed below.\n\n"
        f"Submitted settlement: {submitted_settlement}\n"
        f"Submitted district: {submitted_district or 'not provided'}\n"
        f"Submitted region: {submitted_region or 'not provided'}\n"
        f"Submitted coordinates: {coords}\n\n"
        f"Candidate gazetteer matches (ranked by the automated pipeline):\n{evidence}\n\n"
        "Identify which candidate number (if any) is most plausible, and explain why in no "
        f"more than {MAX_NOTE_WORDS} words. If the evidence above is insufficient to recommend "
        "one confidently, say so explicitly instead of guessing."
    )


def request_reasoning_note(
    *,
    submitted_settlement: str,
    submitted_district: str | None,
    submitted_region: str | None,
    submitted_latitude: float | None,
    submitted_longitude: float | None,
    candidates: list[dict[str, Any]],
    model: str = OLLAMA_MODEL,
    timeout: int = OLLAMA_TIMEOUT_SECONDS,
) -> str | None:
    """Ask a local Ollama model for an advisory note on the ranked candidates.

    Purely advisory - the caller must never let this change the selected
    candidate, confidence score, or decision status, only display it as an
    extra note alongside the analyst's own review. Returns None (not an
    error) whenever Ollama, the requests package, or the request itself
    isn't available, so a down or missing local LLM never blocks matching.
    """
    try:
        import requests
    except ImportError:
        return None

    prompt = build_reasoning_prompt(
        submitted_settlement=submitted_settlement,
        submitted_district=submitted_district,
        submitted_region=submitted_region,
        submitted_latitude=submitted_latitude,
        submitted_longitude=submitted_longitude,
        candidates=candidates,
    )
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        response = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        return text[:400] if text else None
    except Exception:
        return None
