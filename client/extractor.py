# -*- coding: utf-8 -*-
"""
Application data extractor and exporter for BARS.Education.
Fetches declarations, extracts detailed applicant and specialty data,
and exports them to applications.json.
"""

import os
import re
import json
import time
from config import load_client_env, DEFAULT_BARS_URL
from bars_client import BarsClient
from parsers import parse_selected_specialties


def generate_random_app_number() -> str:
    """
    Application numbers are managed centrally on the server via ID_START / ID_SUFFIX.
    Returns empty string so the server auto-assigns sequential application numbers.
    """
    return ""


def fetch_and_export_applications(output_file: str = None) -> list:
    """
    Main workflow for extracting declarations from BARS.Education
    and exporting formatted applications to JSON.
    """
    load_client_env()

    base_url = os.getenv('BARS_BASE_URL', DEFAULT_BARS_URL)
    session_id = os.getenv('SSUZ_SESSIONID', '')
    csrf_token = os.getenv('CSRFTOKEN', '')

    period_id_env = os.getenv('BARS_PERIOD_ID', '').strip()
    limit = int(os.getenv('BARS_LIMIT', 25))
    start = int(os.getenv('BARS_START', 0))

    client = BarsClient(base_url=base_url, session_id=session_id, csrf_token=csrf_token)

    # Determine admission period ID
    period_id = None
    if period_id_env:
        period_id = int(period_id_env)
        print(f"[CLIENT] Using period_id from .env: {period_id}")
    else:
        print("[CLIENT] BARS_PERIOD_ID not set in .env. Requesting periods from server...")
        periods = client.get_periods()
        if periods:
            # Pick latest period (highest ID)
            latest_period = max(periods, key=lambda p: int(p.get("id") or 0))
            period_id = int(latest_period.get("id"))
            period_name = latest_period.get("name") or latest_period.get("__str__") or str(period_id)
            print(f"[CLIENT SUCCESS] Auto-selected latest period: '{period_name}' (ID: {period_id})")
        else:
            period_id = 41
            print(f"[CLIENT WARNING] Could not fetch periods list. Falling back to default period_id: {period_id}")

    # Read filter and sorting parameters from env
    filter_text = (os.getenv('BARS_FILTER') or os.getenv('filter') or '').strip()
    filter_1 = (os.getenv('BARS_FILTER_1') or os.getenv('filter_1') or '').strip()
    filter_2 = (os.getenv('BARS_FILTER_2') or os.getenv('filter_2') or '').strip()

    sort_env = os.getenv('BARS_SORT') if 'BARS_SORT' in os.environ else os.getenv('sort')
    sort_val = sort_env.strip() if sort_env is not None else 'date'

    dir_env = os.getenv('BARS_DIR') if 'BARS_DIR' in os.environ else os.getenv('dir')
    dir_val = dir_env.strip() if dir_env is not None else 'DESC'

    print(f"[CLIENT] Fetching declarations list (start={start}, limit={limit}, period_id={period_id})...")
    if filter_text:
        print(f"   -> Filter (search): {filter_text}")
    if filter_1:
        print(f"   -> Filter 1 (start date): {filter_1}")
    if filter_2:
        print(f"   -> Filter 2 (end date): {filter_2}")
    if sort_val:
        print(f"   -> Sort: {sort_val}")
    if dir_val:
        print(f"   -> Dir: {dir_val}")

    decl_res = client.get_declarations_list(
        period_id=period_id,
        start=start,
        limit=limit,
        sort=sort_val,
        dir_order=dir_val,
        filter_text=filter_text,
        filter_1=filter_1,
        filter_2=filter_2
    )

    rows = decl_res.get("rows", []) if isinstance(decl_res, dict) else []
    print(f"[CLIENT] Server returned {len(rows)} declaration rows.")

    applications_list = []
    gender_map = {"1": "Мужской", "2": "Женский"}

    if rows:
        for idx, row in enumerate(rows, start=1):
            decl_id = row.get("id") or row.get("declaration_id")

            status_obj = row.get("status")
            status_name = ""
            if isinstance(status_obj, dict):
                status_name = str(status_obj.get("name") or "").strip().lower()
            elif isinstance(status_obj, str):
                status_name = status_obj.strip().lower()

            if status_name == "отклонено":
                print(f"[CLIENT] [{idx}/{len(rows)}] Skipping declaration ID={decl_id}: Status is '{status_name}'")
                continue

            print(f"[CLIENT] [{idx}/{len(rows)}] Processing declaration ID={decl_id}...")

            # Query edit window JS/HTML details
            edit_res = client.get_declaration_edit_window(decl_id, period_id=period_id)
            raw_fields = {}

            if isinstance(edit_res, dict):
                if isinstance(edit_res.get("data"), dict):
                    raw_fields.update(edit_res["data"])
                raw_text = edit_res.get("_raw_text") or edit_res.get("raw_text") or ""
                if isinstance(raw_text, str) and raw_text:
                    raw_fields.update(client.parse_extjs_js(raw_text))
            elif isinstance(edit_res, str):
                raw_fields.update(client.parse_extjs_js(edit_res))

            raw_status_obj = raw_fields.get("status")
            raw_status_name = ""
            if isinstance(raw_status_obj, dict):
                raw_status_name = str(raw_status_obj.get("name") or "").strip().lower()
            elif isinstance(raw_status_obj, str):
                raw_status_name = raw_status_obj.strip().lower()

            full_status_name = raw_status_name or status_name
            if full_status_name == "отклонено":
                print(f"[CLIENT] [{idx}/{len(rows)}] Skipping declaration ID={decl_id}: Status is '{full_status_name}'")
                continue

            # Query enrollee details if enrollee ID is available
            enrollee_id = row.get("enrollee_id") or row.get("enrollee") or raw_fields.get("enrollee_id")
            if enrollee_id and (not raw_fields.get("last_name") or not raw_fields.get("passport_series")):
                enrollee_res = client.get_enrollee_details(enrollee_id)
                if isinstance(enrollee_res, dict):
                    if isinstance(enrollee_res.get("data"), dict):
                        raw_fields.update(enrollee_res["data"])
                    e_text = enrollee_res.get("_raw_text") or enrollee_res.get("raw_text") or ""
                    if isinstance(e_text, str) and e_text:
                        raw_fields.update(client.parse_extjs_js(e_text))

            # Merge row fields as fallback
            for k, v in row.items():
                if k not in raw_fields or not raw_fields[k]:
                    raw_fields[k] = v

            # Fallback for last_name / first_name / middle_name from row['fullname'] or row['__str__']
            if not raw_fields.get("last_name"):
                fn = row.get("fullname") or ""
                if not fn and row.get("__str__"):
                    m = re.search(r"Заявление на имя\s+(.+)$", str(row["__str__"]))
                    if m:
                        fn = m.group(1).strip()
                if fn:
                    parts = fn.split()
                    if len(parts) >= 1:
                        raw_fields["last_name"] = parts[0]
                    if len(parts) >= 2:
                        raw_fields["first_name"] = parts[1]
                    if len(parts) >= 3:
                        raw_fields["middle_name"] = " ".join(parts[2:])

            # Query chosen specialties
            raw_text = edit_res.get("_raw_text") or edit_res.get("raw_text") or "" if isinstance(edit_res, dict) else (edit_res if isinstance(edit_res, str) else "")
            win_m = re.search(r"EditWindow\(\{id:'([^']+)'", raw_text)
            m3_window_id = win_m.group(1) if win_m else ""
            grid_m = re.search(r"grid_id['\"\s:]+(['\"])(cmp_[a-f0-9]+)\1", raw_text)
            grid_id = grid_m.group(2) if grid_m else ""

            unit_id = raw_fields.get("unit_id") or 26
            finished_forms = raw_fields.get("finished_forms") or 1

            plans_res = client.get_declaration_plans(
                declaration_id=decl_id,
                period_id=period_id,
                unit_id=unit_id,
                finished_forms=finished_forms,
                m3_window_id=m3_window_id,
                grid_id=grid_id
            )
            plans_rows = plans_res.get("rows", []) if isinstance(plans_res, dict) else []
            selected_specs = parse_selected_specialties(plans_rows)

            app_num = generate_random_app_number()

            app_item = {
                "application_number": app_num,
                "bars_declaration_id": decl_id,
                "portal_app_id": raw_fields.get("add_portal_id_for_declaration_portal_id") or row.get("portal_id") or "",
                "user_epgu_id": raw_fields.get("user_epgu_id") or row.get("user_epgu_id") or "",
                "last_name": raw_fields.get("last_name") or row.get("last_name") or "",
                "first_name": raw_fields.get("first_name") or row.get("first_name") or "",
                "middle_name": raw_fields.get("middle_name") or row.get("middle_name") or "",
                "snils": raw_fields.get("snils") or row.get("snils") or "",
                "passport_series": raw_fields.get("passport_series") or row.get("passport_series") or "",
                "passport_number": raw_fields.get("passport_number") or row.get("passport_number") or "",
                "passport_organization": raw_fields.get("passport_organization") or row.get("passport_organization") or "",
                "passport_issuer_code": raw_fields.get("passport_issuer_code") or row.get("passport_issuer_code") or "",
                "gender": gender_map.get(str(raw_fields.get("gender") or row.get("gender")), "Мужской"),
                "date_of_birth": raw_fields.get("date_of_birth") or row.get("date_of_birth") or "",
                "reg_address_full": raw_fields.get("reg_address_full") or row.get("reg_address_full") or "",
                "selected_specialties": selected_specs,
                "diploma_series": raw_fields.get("diploma_series") or row.get("diploma_series") or "",
                "diploma_number": raw_fields.get("diploma_number") or row.get("diploma_number") or "",
                "diploma_date": raw_fields.get("diploma_date") or row.get("diploma_date") or "",
                "diploma_organization": raw_fields.get("prev_unit") or row.get("prev_unit") or "",
                "average_mark": raw_fields.get("average_mark") or row.get("average_mark") or ""
            }

            fio = f"{app_item['last_name']} {app_item['first_name']} {app_item['middle_name']}".strip()
            specs_names = [s.get('speciality_name') for s in selected_specs if s.get('speciality_name')]
            print(f"   -> BARS Internal ID: {decl_id}")
            print(f"   -> Portal App ID (id заявки на портале): {app_item['portal_app_id'] or 'N/A'}")
            print(f"   -> EPGU User ID (Идентификатор ЕПГУ): {app_item['user_epgu_id'] or 'N/A'}")
            print(f"   -> Entrant Name: {fio or 'N/A'}")
            print(f"   -> Passport: {app_item['passport_series']} {app_item['passport_number']}")
            print(f"   -> Selected Specialties ({len(specs_names)}): {specs_names}")
            if not fio:
                print(f"   [DEBUG] Server row payload keys for ID={decl_id}: {dict(row)}")

            applications_list.append(app_item)
            time.sleep(0.15)
    else:
        # If BARS API returned no rows (offline or session limit), check local parsed_details.json as initial template
        print("[CLIENT INFO] No live rows fetched from BARS API. Checking local template...")
        local_parsed = os.path.join(os.path.dirname(os.path.dirname(__file__)), "parsed_details.json")
        if os.path.exists(local_parsed):
            try:
                with open(local_parsed, "r", encoding="utf-8") as f:
                    single_app = json.load(f)
                    single_app["application_number"] = generate_random_app_number()
                    applications_list.append(single_app)
            except Exception as err:
                print(f"[CLIENT WARNING] Failed to read parsed_details.json: {err}")

    # Write output to client/applications.json
    if not output_file:
        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applications.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(applications_list, f, ensure_ascii=False, indent=2)

    print(f"\n[CLIENT SUCCESS] Exported {len(applications_list)} application(s) to:")
    print(f"   - {output_file}")

    return applications_list
