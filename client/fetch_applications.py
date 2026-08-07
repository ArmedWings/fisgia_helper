# -*- coding: utf-8 -*-
import os
import sys
import json
import random
import re
from bars_client import BarsClient

# Windows 7 Console UTF-8 Fix
if sys.platform == 'win32':
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

def parse_selected_specialties(plans_rows: list) -> list:
    check_fields_map = {
        "regional_budget_study_type_check": "regional_budget_study_type_check",
        "paid_study_type_check": "paid_study_type_check",
        "federal_budget_study_type_check": "federal_budget_study_type_check",
        "municipal_budget_study_type_check": "municipal_budget_study_type_check",
        "foreign_quota_study_type_check": "foreign_quota_study_type_check"
    }
    selected = []
    for row in plans_rows:
        active_checks = {}
        for src_field, target_field in check_fields_map.items():
            val = row.get(src_field)
            if val is True or val == 1 or str(val).lower() == "true":
                active_checks[target_field] = True

        if active_checks:
            spec_name = row.get("speciality_name") or row.get("name") or row.get("specialization_name")
            item = {
                "speciality_name": spec_name or "\u0421\u043f\u0435\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
                "speciality_program_type_name": row.get("speciality_program_type_name") or "\u041f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430 \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0438 \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0441\u0442\u043e\u0432 \u0441\u0440\u0435\u0434\u043d\u0435\u0433\u043e \u0437\u0432\u0435\u043d\u0430"
            }
            item.update(active_checks)
            selected.append(item)
    return selected

def generate_random_app_number():
    rand_digits = random.randint(10000, 99999)
    return f"{rand_digits}-26"

def fetch_and_export_applications():
    client_dir = os.path.dirname(__file__)
    for filename in ['config.env', '.env']:
        env_path = os.path.join(client_dir, filename)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            if k and k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass

    base_url = os.getenv('BARS_BASE_URL', 'https://xn--n1abf.xn--33-6kcadhwnl3cfdx.xn--p1ai')
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

    print(f"[CLIENT] Fetching declarations list (start={start}, limit={limit}, period_id={period_id})...")
    decl_res = client.get_declarations_list(period_id=period_id, start=start, limit=limit)

    rows = decl_res.get("rows", []) if isinstance(decl_res, dict) else []
    print(f"[CLIENT] Server returned {len(rows)} declaration rows.")

    applications_list = []
    gender_map = {"1": "\u041c\u0443\u0436\u0441\u043a\u043e\u0439", "2": "\u0416\u0435\u043d\u0441\u043a\u0438\u0439"}

    if rows:
        for idx, row in enumerate(rows, start=1):
            decl_id = row.get("id") or row.get("declaration_id")
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
                    m = re.search(r"\u0417\u0430\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0430 \u0438\u043c\u044f\s+(.+)$", str(row["__str__"]))
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
                "portal_app_id": raw_fields.get("add_portal_id_for_declaration_portal_id") or row.get("add_portal_id_for_declaration_portal_id") or row.get("portal_id") or "",
                "user_epgu_id": raw_fields.get("user_epgu_id") or row.get("user_epgu_id") or "",
                "last_name": raw_fields.get("last_name") or raw_fields.get("surname") or row.get("last_name") or row.get("surname") or "",
                "first_name": raw_fields.get("first_name") or raw_fields.get("firstname") or row.get("first_name") or row.get("firstname") or "",
                "middle_name": raw_fields.get("middle_name") or raw_fields.get("patronymic") or row.get("middle_name") or row.get("patronymic") or "",
                "snils": raw_fields.get("snils") or row.get("snils") or "",
                "passport_series": raw_fields.get("passport_series") or row.get("passport_series") or "",
                "passport_number": raw_fields.get("passport_number") or row.get("passport_number") or "",
                "passport_organization": raw_fields.get("passport_organization") or row.get("passport_organization") or "",
                "passport_issuer_code": raw_fields.get("passport_issuer_code") or row.get("passport_issuer_code") or "",
                "gender": gender_map.get(str(raw_fields.get("gender") or row.get("gender")), "\u041c\u0443\u0436\u0441\u043a\u043e\u0439"),
                "date_of_birth": raw_fields.get("date_of_birth") or row.get("date_of_birth") or "",
                "reg_address_full": raw_fields.get("reg_address_full") or row.get("reg_address_full") or "",
                "selected_specialties": selected_specs,
                "diploma_number": raw_fields.get("diploma_number") or row.get("diploma_number") or "",
                "diploma_date": raw_fields.get("diploma_date") or row.get("diploma_date") or "",
                "diploma_organization": raw_fields.get("prev_unit") or row.get("prev_unit") or ""
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
    else:
        # If BARS API returned no rows (offline or session limit), check local parsed_details.json as initial template
        print("[CLIENT INFO] No live rows fetched from BARS API. Checking local template...")
        local_parsed = os.path.join(os.path.dirname(os.path.dirname(__file__)), "parsed_details.json")
        if os.path.exists(local_parsed):
            with open(local_parsed, "r", encoding="utf-8") as f:
                single_app = json.load(f)
                single_app["application_number"] = generate_random_app_number()
                applications_list.append(single_app)

    # Write output to client/applications.json and copy to server/applications.json
    client_out = os.path.join(os.path.dirname(__file__), "applications.json")
    server_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
    os.makedirs(server_dir, exist_ok=True)
    server_out = os.path.join(server_dir, "applications.json")

    with open(client_out, "w", encoding="utf-8") as f:
        json.dump(applications_list, f, ensure_ascii=False, indent=2)

    with open(server_out, "w", encoding="utf-8") as f:
        json.dump(applications_list, f, ensure_ascii=False, indent=2)

    print(f"\n[CLIENT SUCCESS] Exported {len(applications_list)} application(s) to:")
    print(f"   - {client_out}")
    print(f"   - {server_out}")

if __name__ == "__main__":
    fetch_and_export_applications()
