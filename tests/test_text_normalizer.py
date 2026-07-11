from __future__ import annotations

import numpy as np
import pandas as pd

from backend.text_normalizer import normalize_place_name


def test_empty_and_missing_values_are_safe():
    assert normalize_place_name(None) == ""
    assert normalize_place_name("") == ""
    assert normalize_place_name("   ") == ""
    assert normalize_place_name(np.nan) == ""
    assert normalize_place_name(pd.NA) == ""


def test_trims_and_collapses_repeated_spaces():
    assert normalize_place_name("  Baidoa   Town  ") == "baidoa town"


def test_normalizes_capitalization():
    assert normalize_place_name("BAIDOA") == "baidoa"
    assert normalize_place_name("BaiDoa") == "baidoa"


def test_normalizes_unicode_diacritics():
    assert normalize_place_name("Muqdisho") == normalize_place_name("Muqdisho")
    assert normalize_place_name("Café Town") == "cafe town"


def test_standardizes_apostrophe_variants_without_deleting_them():
    straight = normalize_place_name("Ma'moura")
    curly = normalize_place_name("Ma’moura")
    backtick = normalize_place_name("Ma`moura")
    assert straight == curly == backtick == "ma'moura"


def test_standardizes_hyphen_variants_without_collapsing_to_space():
    en_dash = normalize_place_name("Belet–Weyne")
    em_dash = normalize_place_name("Belet—Weyne")
    plain = normalize_place_name("Belet-Weyne")
    assert en_dash == em_dash == plain == "belet-weyne"


def test_removes_unnecessary_punctuation():
    assert normalize_place_name("Baidoa, District!") == "baidoa district"
    assert normalize_place_name("Baidoa (Town)") == "baidoa town"


def test_strip_generic_suffixes_disabled_by_default():
    assert normalize_place_name("Buulo Xaaji IDP Camp") == "buulo xaaji idp camp"


def test_strip_generic_suffixes_when_enabled():
    assert normalize_place_name("Buulo Xaaji IDP Camp", strip_generic_suffixes=True) == "buulo xaaji"
    assert normalize_place_name("Baidoa Village", strip_generic_suffixes=True) == "baidoa"
    assert normalize_place_name("Baidoa Town", strip_generic_suffixes=True) == "baidoa"
    assert normalize_place_name("Kaharey Settlement", strip_generic_suffixes=True) == "kaharey"


def test_strip_generic_suffix_does_not_remove_the_only_content():
    # "Camp" alone is the entire submitted value; there is nothing meaningful
    # left to fall back to, so it must not be stripped down to an empty string.
    assert normalize_place_name("Camp", strip_generic_suffixes=True) == "camp"


def test_preserves_meaningful_somali_name_components():
    assert normalize_place_name("Qardho") == "qardho"
    assert normalize_place_name("Buuhoodle") == "buuhoodle"
    assert normalize_place_name("Xudur") == "xudur"


def test_idempotent_on_already_normalized_input():
    once = normalize_place_name("Belet-Weyne, IDP Camp")
    twice = normalize_place_name(once)
    assert once == twice
