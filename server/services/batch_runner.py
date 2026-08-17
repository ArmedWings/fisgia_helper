# -*- coding: utf-8 -*-
"""
Batch processor and runner for FIS GIA application submissions.
Manages input JSON resolution, auto-incrementing application counters,
retry logic for existing application numbers, rate limiting, and dual logging.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from core.config import FIS_BASE_URL
from core.logger import TeeLogger
from core.helpers import load_json_file
from services.specialties import load_specialty_prefix_map
from services.fis_client import refresh_session_auth, auto_discover_campaign_params
from services.submission import submit_single_application


def run_fis_submission(json_file=None):
    """
    Main batch runner for submitting applications to FIS GIA.
    """
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    logs_dir = os.path.join(server_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_filename = os.path.join(logs_dir, f"log_{now_str}.txt")
    response_filename = os.path.join(logs_dir, f"response_{now_str}.json")

    tee_logger = TeeLogger(log_filename)
    sys.stdout = tee_logger

    # Ensure prefix map is loaded
    load_specialty_prefix_map()

    # Determine input JSON file path
    if not json_file or str(json_file).startswith("--") or str(json_file).lower() in ["dev", "prod"]:
        json_file = None
        for arg in sys.argv[1:]:
            if not arg.startswith("--") and arg.lower() not in ["dev", "prod"]:
                if arg.endswith(".json") or os.path.exists(arg):
                    json_file = arg
                    break

    if not json_file:
        candidate_json_paths = [
            os.path.join(server_dir, "applications.json"),
            os.path.join(os.path.dirname(server_dir), "client", "applications.json"),
            os.path.join(server_dir, "parsed_details.json"),
            os.path.join(os.getcwd(), "applications.json"),
            os.path.join(os.getcwd(), "parsed_details.json"),
        ]
        for p in candidate_json_paths:
            if os.path.exists(p):
                json_file = p
                break

    if not json_file:
        json_file = os.path.join(server_dir, "parsed_details.json")

    print(f"=== FIS GIA APPLICATION SUBMISSION RUNNER ({now_str}) ===")
    print(f"Loading applications data from: {json_file}")

    if not os.path.exists(json_file):
        print(f"[CRITICAL ERROR] Applications file not found: {json_file}")
        return

    try:
        raw_input = load_json_file(json_file)
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to parse JSON file {json_file}: {e}")
        return

    if isinstance(raw_input, dict):
        applications_list = [raw_input]
    elif isinstance(raw_input, list):
        applications_list = raw_input
    else:
        print("[CRITICAL ERROR] Invalid JSON structure. Must be object or array.")
        return

    print(f"Found {len(applications_list)} application(s) to process.")

    target_url = FIS_BASE_URL
    s = requests.Session()
    access_token = refresh_session_auth(s, target_url)

    cookie_str = "gvuz.cookie=n; fisTokenIsValid=True"
    if access_token:
        cookie_str += "; fisAccess=" + str(access_token)

    headers_json = {
        "Accept": "application/json, text/javascript, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json; charset=UTF-8",
        "Cookie": cookie_str,
        "Origin": target_url,
        "Referer": target_url + "/Application/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    if access_token:
        headers_json["Authorization"] = "Bearer " + str(access_token)

    # Dynamic Warmup Discovery
    discovered_config = auto_discover_campaign_params(s, target_url, headers_json)

    summary_responses = []

    # Application ID Counter Setup from env (ID_START, ID_SUFFIX)
    id_start_val = int(os.getenv("ID_START", "294"))
    id_suffix_val = os.getenv("ID_SUFFIX", "-26")
    current_app_counter = id_start_val

    abort_batch = False

    # Batch Processing Loop with CONTINUE ON ERROR
    for idx, app_data in enumerate(applications_list, start=1):
        raw_app_num = str(app_data.get("application_number") or app_data.get("app_number") or "").strip()

        if not raw_app_num:
            assigned_app_num = f"{current_app_counter}{id_suffix_val}"
            app_data["application_number"] = assigned_app_num
            app_num = assigned_app_num
            print(f"\n=================================================================")
            print(f"   [BATCH {idx}/{len(applications_list)}] Submitting Application #{assigned_app_num} (Auto-assigned counter: {current_app_counter})")
            print(f"=================================================================")
        else:
            app_num = raw_app_num
            print(f"\n=================================================================")
            print(f"   [BATCH {idx}/{len(applications_list)}] Submitting Application #{app_num} (Provided from input data)")
            print(f"=================================================================")

        max_retries = 5
        res = None
        for attempt in range(1, max_retries + 1):
            try:
                res = submit_single_application(s, target_url, headers_json, app_data, discovered_config)
                res_status = res.get("status")

                if res_status == "ERROR_APP_NUMBER_EXISTS":
                    if idx == 1 and attempt == 1:
                        print("\n=================================================================")
                        print(f"[CRITICAL ABORT] Starting application number '{app_num}' is already in use on FIS GIA server!")
                        print("   -> Please select a different starting application number (ID_START) in your dev.env / prod.env file and restart.")
                        print("=================================================================")
                        summary_responses.append(res)
                        abort_batch = True
                        break

                    if attempt < max_retries and not raw_app_num:
                        current_app_counter += 1
                        assigned_app_num = f"{current_app_counter}{id_suffix_val}"
                        app_data["application_number"] = assigned_app_num
                        app_num = assigned_app_num
                        print(f"   [RETRY {attempt}/{max_retries}] Application number in use. Advancing counter to {current_app_counter} ({assigned_app_num}) and retrying...")
                        time.sleep(1.0)
                        continue
                    elif attempt == max_retries:
                        print(f"\n[CRITICAL ERROR] Failed to find available application number after {max_retries} retries for batch item #{idx}.")
                        summary_responses.append(res)
                        abort_batch = True
                        break

                summary_responses.append(res)
                if res_status in ["CREATED", "PARTIAL_SUCCESS"]:
                    if not raw_app_num:
                        current_app_counter += 1
                elif res_status in ["ALREADY_EXISTS", "ERROR_UNMATCHED_SPECIALTY"]:
                    if not raw_app_num:
                        print(f"   [COUNTER RE-USE] Keeping counter at {current_app_counter} for next entrant.")
                break

            except Exception as e:
                print(f"[EXCEPTION ERROR] Failed to submit application #{app_num}: {e}")
                res = {
                    "application_number": str(app_num),
                    "passport_series": str(app_data.get("passport_series", "")),
                    "passport_number": str(app_data.get("passport_number", "")),
                    "status": "ERROR",
                    "message": f"Execution Exception: {str(e)}"
                }
                summary_responses.append(res)
                break

        if abort_batch:
            break

        # Safety rate-limiting delay between applications to avoid HTTP 429 / server block
        if idx < len(applications_list):
            time.sleep(1.5)

    # Write summary response JSON
    with open(response_filename, "w", encoding="utf-8") as f:
        json.dump(summary_responses, f, ensure_ascii=False, indent=2)

    cnt_created = sum(1 for r in summary_responses if r.get("status") == "CREATED")
    cnt_already = sum(1 for r in summary_responses if r.get("status") == "ALREADY_EXISTS")
    cnt_partial = sum(1 for r in summary_responses if r.get("status") == "PARTIAL_SUCCESS")
    cnt_error = sum(1 for r in summary_responses if "ERROR" in str(r.get("status", "")))

    print("\n=================================================================")
    print("   BATCH PROCESSING FINISHED SUMMARY")
    print(f"   Total Processed: {len(summary_responses)}")
    print(f"   - Successfully Created (CREATED):            {cnt_created}")
    print(f"   - Already Exists / Skipped (ALREADY_EXISTS): {cnt_already}")
    print(f"   - Partial Success (PARTIAL_SUCCESS):         {cnt_partial}")
    print(f"   - Errors (ERROR):                            {cnt_error}")
    print(f"   Console Log Saved: {log_filename}")
    print(f"   Response JSON Saved: {response_filename}")
    print("=================================================================")

    try:
        sys.stdout = tee_logger.terminal
        tee_logger.close()
    except Exception:
        pass

    return summary_responses
