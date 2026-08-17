# -*- coding: utf-8 -*-
"""
Parsing and data transformation utilities for BARS.Education API responses.
"""

import re


def format_date_filter(val: str) -> str:
    """
    Converts date string from dd.mm.yyyy (or dd.mm.yyyy HH:MM:SS) to ISO format yyyy-mm-ddThh:mm:ss.
    If already in ISO format or empty, returns as is.
    """
    if not val:
        return ""
    val = str(val).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', val):
        return val
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{1,2}):(\d{1,2}))?$', val)
    if m:
        day, month, year, hh, mm, ss = m.groups()
        day = day.zfill(2)
        month = month.zfill(2)
        hh = (hh or "00").zfill(2)
        mm = (mm or "00").zfill(2)
        ss = (ss or "00").zfill(2)
        return f"{year}-{month}-{day}T{hh}:{mm}:{ss}"
    return val


def parse_extjs_js(js_content: str) -> dict:
    """
    Parses ExtJS UI definitions from raw JavaScript strings to extract
    field names and their corresponding values or defaultText.
    """
    if not js_content or not isinstance(js_content, str):
        return {}

    extracted_data = {}
    pattern = re.compile(
        r"name\s*:\s*['\"](?P<name>[^'\"]+)['\"]"
        r"(?:(?!new Ext\.).)*?"
        r"(?:value\s*:\s*(?P<val_str>'[^']*'|\"[^\"]*\"|\d+(?:\.\d+)?|true|false)|defaultText\s*:\s*['\"](?P<def_text>[^'\"]+)['\"])",
        re.DOTALL
    )
    for match in pattern.finditer(js_content):
        name = match.group('name')
        val_str = match.group('val_str')
        def_text = match.group('def_text')

        if val_str:
            if (val_str.startswith("'") and val_str.endswith("'")) or (val_str.startswith('"') and val_str.endswith('"')):
                val = val_str[1:-1]
            else:
                val = val_str
        elif def_text:
            val = def_text
        else:
            val = ""

        if name not in extracted_data or val != "":
            extracted_data[name] = val

    return extracted_data


def parse_selected_specialties(plans_rows: list) -> list:
    """
    Parses education plan rows from BARS declaration and extracts selected specialties
    along with active study type flags (budget, paid, quota, etc.).
    """
    if not plans_rows or not isinstance(plans_rows, list):
        return []

    check_fields_map = {
        "regional_budget_study_type_check": "regional_budget_study_type_check",
        "paid_study_type_check": "paid_study_type_check",
        "federal_budget_study_type_check": "federal_budget_study_type_check",
        "municipal_budget_study_type_check": "municipal_budget_study_type_check",
        "foreign_quota_study_type_check": "foreign_quota_study_type_check"
    }

    selected = []
    for row in plans_rows:
        if not isinstance(row, dict):
            continue

        active_checks = {}
        for src_field, target_field in check_fields_map.items():
            val = row.get(src_field)
            if val is True or val == 1 or str(val).lower() == "true":
                active_checks[target_field] = True

        if active_checks:
            spec_name = row.get("speciality_name") or row.get("name") or row.get("specialization_name")
            item = {
                "speciality_name": spec_name or "Специальность",
                "speciality_program_type_name": row.get("speciality_program_type_name") or "Программа подготовки специалистов среднего звена"
            }
            item.update(active_checks)
            selected.append(item)

    return selected
