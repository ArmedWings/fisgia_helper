# -*- coding: utf-8 -*-
"""
Specialty prefix mapping and fuzzy matching against FIS GIA competitive groups.
"""

import os
import sys
import re

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from core.helpers import extract_numeric_suffix, load_json_file

_CACHED_PREFIX_MAP = None


def load_specialty_prefix_map(filepath=None, force_reload=False):
    """
    Loads and caches specialty prefix mappings from specialties.json.
    """
    global _CACHED_PREFIX_MAP
    if _CACHED_PREFIX_MAP is not None and not force_reload and filepath is None:
        return _CACHED_PREFIX_MAP

    if not filepath:
        filepath = os.path.join(server_dir, "specialties.json")

    if not os.path.exists(filepath):
        print(f"[WARNING] Specialties mapping file not found at: {filepath}")
        return []

    try:
        raw_data = load_json_file(filepath)
        prefix_map = []
        for item in raw_data:
            kws = tuple([kw.lower().strip() for kw in item.get("keywords", [])])
            prefs = item.get("prefixes", [])
            prefix_map.append((kws, prefs))

        if filepath is None or filepath.endswith("specialties.json"):
            _CACHED_PREFIX_MAP = prefix_map

        return prefix_map
    except Exception as e:
        print(f"[ERROR] Failed to load specialties mapping file {filepath}: {e}")
        return []


def resolve_competitive_group_ids_with_names(spec_name, dynamic_cg_map, prefix_map=None):
    """
    Matches a specialty title (from application) to registered Competitive Group IDs in FIS GIA
    using keyword prefix mappings.
    Returns: (matched_ids, matched_names)
    """
    if not spec_name or not dynamic_cg_map:
        return [], []

    if prefix_map is None:
        prefix_map = load_specialty_prefix_map()

    spec_lower = str(spec_name).strip().lower()

    target_prefixes = []
    for keywords, prefixes in prefix_map:
        if any(kw in spec_lower for kw in keywords):
            for p in prefixes:
                if p not in target_prefixes:
                    target_prefixes.append(p)
            break

    if not target_prefixes:
        return [], []

    matched_pairs = []

    for pref_idx, pref in enumerate(target_prefixes):
        pref_clean = pref.upper().strip()

        pref_base_match = re.search(r'^[A-ZА-яЁё]+', pref_clean)
        pref_base = pref_base_match.group(0) if pref_base_match else pref_clean

        for cg_name, cg_id in dynamic_cg_map.items():
            cg_clean = str(cg_name).upper().strip()

            cg_base_match = re.search(r'^[A-ZА-яЁё]+', cg_clean)
            cg_base = cg_base_match.group(0) if cg_base_match else ""

            is_match = False

            if "-" in pref_clean or (any(c.isdigit() for c in pref_clean) and len(pref_clean) > len(pref_base)):
                if cg_clean == pref_clean or cg_clean.startswith(pref_clean + "-") or cg_clean.startswith(pref_clean):
                    is_match = True
            else:
                if cg_base == pref_base:
                    is_match = True

            if is_match:
                if not any(item[3] == cg_id for item in matched_pairs):
                    num = extract_numeric_suffix(cg_clean)
                    matched_pairs.append((pref_idx, num, cg_name, cg_id))

    matched_pairs.sort(key=lambda x: (x[0], x[1]))

    matched_ids = [item[3] for item in matched_pairs]
    matched_names = [item[2] for item in matched_pairs]

    return matched_ids, matched_names
