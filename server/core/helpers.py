# -*- coding: utf-8 -*-
"""
Helper utility functions for data parsing, ID extraction, address handling, and GPA formatting.
"""

import re
import json
from .config import REGION_MAP


def load_json_file(filepath):
    """
    Safely loads and parses a JSON file with automatic encoding fallback (UTF-8-SIG -> CP1251).
    """
    with open(filepath, "rb") as f:
        content = f.read()

    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(content.decode("cp1251"))


def format_gpa(val):
    """
    Formats GPA value (average mark) to a Russian-decimal string with 4 decimal places (e.g. 4,5000).
    Returns None if value is missing, invalid, or out of range (0, 5].
    """
    if val is None or str(val).strip() in ("", "None", "null"):
        return None
    try:
        val_str = str(val).replace(",", ".").strip()
        val_float = float(val_str)
        if val_float <= 0 or val_float > 5:
            return None
        return f"{val_float:.4f}".replace(".", ",")
    except (ValueError, TypeError):
        return None


def extract_id(d, *keys):
    """
    Extracts an integer ID from a dictionary given candidate keys.
    Performs case-sensitive search first, followed by case-insensitive fallback.
    """
    if not isinstance(d, dict):
        return None

    for k in keys:
        val = d.get(k)
        if val is not None and str(val).strip() != "" and str(val) != "0" and str(val).lower() != "none":
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    d_lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        val = d_lower.get(str(k).lower())
        if val is not None and str(val).strip() != "" and str(val) != "0" and str(val).lower() != "none":
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    return None


def get_region_id(text_string):
    """
    Resolves FIS GIA Region ID from address string using REGION_MAP.
    Defaults to '33' (Vladimir Region).
    """
    if not text_string:
        return "33"
    t_lower = text_string.lower()
    for key, reg_id in REGION_MAP.items():
        if key in t_lower:
            return reg_id
    return "33"


def get_town_type_id(address, region_id="33"):
    """
    Determines TownTypeID in FIS GIA:
    1 = City of Federal Significance (Moscow, Saint Petersburg, Sevastopol)
    2 = City / Town
    4 = Rural / Other
    """
    if not address:
        return "4"
    if str(region_id) in ["77", "78", "92"]:
        return "1"

    if re.search(r" г | г\.|^г\.|^г ", address, re.IGNORECASE) or "город" in address.lower():
        return "2"

    return "4"


def extract_numeric_suffix(name):
    """
    Extracts integer digits from a string (e.g. 'МР-126' -> 126).
    """
    m = re.search(r'\d+', str(name))
    return int(m.group(0)) if m else 0
