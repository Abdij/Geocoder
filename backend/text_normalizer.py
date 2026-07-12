from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

# Curly/backtick apostrophe variants standardized to a plain "'" rather than
# stripped, since Somali transliterations sometimes use an apostrophe for a
# glottal stop (e.g. "Ma'moura") - dropping it could conflate distinct names.
_APOSTROPHE_VARIANTS = "‘’ʼʻ´`"

# En/em dash and similar variants standardized to a plain "-" rather than
# collapsed to a space, since hyphens can be a structural part of a place
# name (e.g. "Belet-Weyne").
_HYPHEN_VARIANTS = "‐‑‒–—―−"

# Checked longest-phrase-first so "idp camp" strips as a unit instead of
# leaving a dangling "idp" behind after only "camp" matches. Facility-type
# terms (health center, mch, otp, tsfp, ...) were added because humanitarian
# response data frequently submits a facility name (e.g. "Kaharey Health
# Center") in the settlement-name field instead of the settlement itself,
# which otherwise tanks fuzzy name-matching against a plain settlement
# gazetteer.
_GENERIC_SUFFIXES = (
    "idp camp",
    "idp settlement",
    "idp site",
    "therapeutic feeding center",
    "therapeutic feeding centre",
    "nutrition center",
    "nutrition centre",
    "mobile clinic",
    "mobile team",
    "mobile outreach",
    "health center",
    "health centre",
    "district hospital",
    "settlement",
    "village",
    "town",
    "camp",
    "hospital",
    "clinic",
    "outreach",
    "center",
    "centre",
    "mch",
    "otp",
    "tsfp",
    "hc",
)

_PUNCTUATION_PATTERN = re.compile(r"[^a-z0-9\s'\-]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_HYPHEN_RUN_PATTERN = re.compile(r"-{2,}")
_HYPHEN_SPACING_PATTERN = re.compile(r"\s*-\s*")


def normalize_place_name(value: Any, strip_generic_suffixes: bool = False) -> str:
    """Normalize a place name for matching while preserving Somali name intent.

    Trims, collapses whitespace, normalizes unicode, standardizes apostrophe
    and hyphen variants, strips other punctuation, and lowercases. Hyphens
    and apostrophes are kept rather than stripped, since they can be
    phonetically or structurally meaningful in Somali place names.

    The caller is responsible for preserving the original submitted value
    separately (this function only returns the derived normalized form).
    """
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    for variant in _APOSTROPHE_VARIANTS:
        text = text.replace(variant, "'")
    for variant in _HYPHEN_VARIANTS:
        text = text.replace(variant, "-")

    text = text.lower()
    text = _PUNCTUATION_PATTERN.sub(" ", text)
    text = _HYPHEN_SPACING_PATTERN.sub("-", text)
    text = _HYPHEN_RUN_PATTERN.sub("-", text)
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    text = text.strip("-'")

    if strip_generic_suffixes and text:
        # Loop so chained noise ("Kaharey Health Center IDP Camp") is fully
        # peeled off, not just the outermost suffix. Capped at len(_GENERIC_SUFFIXES)
        # so a pathological input can't loop indefinitely.
        for _ in range(len(_GENERIC_SUFFIXES)):
            stripped_any = False
            for suffix in _GENERIC_SUFFIXES:
                match = re.match(rf"^(.*?)\s+{re.escape(suffix)}$", text)
                if match and match.group(1).strip():
                    text = match.group(1).strip()
                    stripped_any = True
                    break
            if not stripped_any:
                break

    return text
