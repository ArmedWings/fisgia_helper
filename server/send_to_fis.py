# -*- coding: utf-8 -*-
"""
FIS GIA Integration Script for Windows 7
Processes applications list JSON and submits applications to FIS GIA via REST API.
"""

import os
import sys
import re
import json
import time
import requests
from datetime import datetime

# Windows 7 Console UTF-8 Fix
if sys.platform == 'win32':
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

# Pure Python config.env / .env parser with env_mode support (dev.env / prod.env)
def _load_server_env():
    server_dir = os.path.dirname(os.path.abspath(__file__))

    # Determine env mode (--prod, --dev, --env=prod, --env=dev, or os.environ APP_ENV/ENV_MODE, default 'dev')
    env_mode = os.getenv("APP_ENV", os.getenv("ENV_MODE", "dev")).lower().strip()
    for arg in sys.argv:
        if arg.startswith("--env="):
            env_mode = arg.split("=", 1)[1].lower().strip()
        elif arg.lower() in ["--prod", "prod"]:
            env_mode = "prod"
        elif arg.lower() in ["--dev", "dev"]:
            env_mode = "dev"

    os.environ["APP_ENV"] = env_mode

    candidate_files = [
        f"{env_mode}.env",
        f"{env_mode}.config.env",
        "config.env",
        ".env"
    ]

    loaded_file = None
    for fname in candidate_files:
        for search_dir in [server_dir, os.path.dirname(server_dir), os.getcwd()]:
            filepath = os.path.join(search_dir, fname)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                k, v = line.split('=', 1)
                                k = k.strip()
                                v = v.strip().strip("'").strip('"')
                                if k:
                                    os.environ[k] = v
                    loaded_file = filepath
                    break
                except Exception:
                    pass
        if loaded_file:
            break
    print(f"[CONFIG] Active Environment: {env_mode.upper()} (Loaded from: {loaded_file or 'OS Environment'})")
    return env_mode

_load_server_env()

# ------------------------------------------------------------------------------
# CENTRAL CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------------------
FIS_BASE_URL = os.getenv("FIS_BASE_URL", "http://10.0.3.1:8383").rstrip('/')

def load_specialty_prefix_map(filepath=None):
    if not filepath:
        server_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(server_dir, "specialties.json")

    if not os.path.exists(filepath):
        print(f"[WARNING] Specialties mapping file not found at: {filepath}")
        return []

    try:
        with open(filepath, "rb") as f:
            content = f.read()
        try:
            raw_data = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_data = json.loads(content.decode("cp1251"))

        prefix_map = []
        for item in raw_data:
            kws = tuple([kw.lower().strip() for kw in item.get("keywords", [])])
            prefs = item.get("prefixes", [])
            prefix_map.append((kws, prefs))
        return prefix_map
    except Exception as e:
        print(f"[ERROR] Failed to load specialties mapping file {filepath}: {e}")
        return []

SPECIALTY_PREFIX_MAP = load_specialty_prefix_map()

REGION_MAP = {
    "\u0432\u043b\u0430\u0434\u0438\u043c\u0438\u0440": "33",
    "\u043c\u043e\u0441\u043a\u0432": "77",
    "\u043c\u043e\u0441\u043a\u043e\u0432\u0441\u043a": "50",
    "\u0438\u0432\u0430\u043d\u043e\u0432": "37",
    "\u043d\u0438\u0436\u0435\u0433\u043e\u0440\u043e\u0434": "52",
    "\u043d\u0438\u0436\u043d\u0438\u0439 \u043d\u043e\u0432\u0433\u043e\u0440\u043e\u0434": "52",
    "\u0440\u044f\u0437\u0430\u043d": "62",
    "\u044f\u0440\u043e\u0441\u043b\u0430\u0432\u043b": "76",
    "\u0442\u0432\u0435\u0440": "69",
    "\u0442\u0443\u043b": "71",
    "\u043a\u0430\u043b\u0443\u0433": "40",
    "\u043f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433": "78"
}

DEFAULT_SETTINGS = {
    "default_app_number": "294-19",
    "registration_date": "05.08.2019",
    "status_id": 1,
    "is_epgu": True
}

# Authorization Tokens from Environment (.env)
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")

class LoggerWriter:
    """Tee logger to write stdout both to console and log file."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def format_gpa(val):
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

def get_entrant_id_from_server(s, target_url, headers_json, app_id, j0):
    eid = extract_id(j0.get("Data") if isinstance(j0, dict) else {}, "EntrantID", "EntrantId") or extract_id(j0 if isinstance(j0, dict) else {}, "EntrantID", "EntrantId")
    pid = extract_id(j0.get("Data") if isinstance(j0, dict) else {}, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID") or extract_id(j0 if isinstance(j0, dict) else {}, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID")
    if eid:
        return eid, pid

    headers_html = dict(headers_json)
    headers_html["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        r_wz1 = s.get(target_url + f"/Application/Wz1?id={app_id}", headers=headers_html)
        text_wz1 = r_wz1.text if r_wz1.status_code == 200 else ""

        if not text_wz1 or len(text_wz1) < 50:
            r_wz1_post = s.post(target_url + "/Application/Wz1", json={"id": int(app_id)}, headers=headers_json)
            if r_wz1_post.status_code == 200:
                text_wz1 = r_wz1_post.text

        if text_wz1:
            if text_wz1.strip().startswith('{'):
                try:
                    j_wz1 = json.loads(text_wz1)
                    data_wz1 = j_wz1.get("Data") or j_wz1
                    eid = extract_id(data_wz1, "EntrantID", "EntrantId") or eid
                    pid = extract_id(data_wz1, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID") or pid
                except Exception:
                    pass

            if not eid:
                match = re.search(r'<input[^>]*id=["\']EntrantID["\'][^>]*value=["\'](\d+)["\']', text_wz1, re.IGNORECASE) or \
                        re.search(r'<input[^>]*name=["\']EntrantID["\'][^>]*value=["\'](\d+)["\']', text_wz1, re.IGNORECASE) or \
                        re.search(r'<input[^>]*value=["\'](\d+)["\'][^>]*id=["\']EntrantID["\']', text_wz1, re.IGNORECASE) or \
                        re.search(r'<input[^>]*value=["\'](\d+)["\'][^>]*name=["\']EntrantID["\']', text_wz1, re.IGNORECASE) or \
                        re.search(r'EntrantID["\s:=]+(\d+)', text_wz1, re.IGNORECASE)
                if match:
                    eid = int(match.group(1))
    except Exception as err:
        print(f"   [WARNING] Failed to query /Application/Wz1: {err}")

    return eid, pid

def get_passport_doc_id(s, target_url, headers_json, app_id, edu_doc_id, entrant_id=None, j0=None, j1=None):
    # 1. Query /Entrant/getEntrantDocuments directly by EntrantID (AUTHORITATIVE SOURCE)
    if entrant_id:
        try:
            r_docs = s.post(target_url + "/Entrant/getEntrantDocuments", json={"EntrantID": str(entrant_id)}, headers=headers_json)
            if r_docs.status_code == 200:
                j_docs = r_docs.json()
                if isinstance(j_docs, dict) and not j_docs.get("IsError") and isinstance(j_docs.get("Data"), list):
                    for doc in j_docs["Data"]:
                        dt_id = doc.get("DocumentTypeID")
                        dt_name = str(doc.get("DocumentTypeName", "")).lower()
                        if dt_id == 1 or "\u043f\u0430\u0441\u043f\u043e\u0440\u0442" in dt_name:
                            p_id = doc.get("EntrantDocumentID")
                            if p_id and int(p_id) > 0:
                                return int(p_id)
        except Exception as e:
            print(f"   [WARNING] Failed to query getEntrantDocuments: {e}")

    # 2. Check j1 / j0 JSON responses
    for source in [j1, j0]:
        if isinstance(source, dict):
            pid = extract_id(source.get("Data"), "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID") or \
                  extract_id(source, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID")
            if pid and pid > 10000000 and pid != int(edu_doc_id):
                return pid

    return None

def get_region_id(text_string):
    if not text_string:
        return "33"
    t_lower = text_string.lower()
    for key, reg_id in REGION_MAP.items():
        if key in t_lower:
            return reg_id
    return "33"

def get_town_type_id(address, region_id="33"):
    if not address:
        return "4"
    if str(region_id) in ["77", "78", "92"]:
        return "1"

    if re.search(r" \u0433 | \u0433\.|^\u0433\.|^\u0433 ", address, re.IGNORECASE) or "\u0433\u043e\u0440\u043e\u0434" in address.lower():
        return "2"

    return "4"

def refresh_session_auth(session, target_url):
    print("[AUTH] Warming up session and refreshing access token...")
    auth_urls = [
        target_url + "/Account/Refresh",
        target_url + "/Account/RefreshToken",
        target_url + "/api/account/refresh"
    ]
    payload = {
        "accessToken": ACCESS_TOKEN,
        "refreshToken": REFRESH_TOKEN
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8"
    }

    access_token = ACCESS_TOKEN
    for url in auth_urls:
        try:
            r = session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                j = r.json()
                access_token = j.get("access_token") or j.get("fisAccess") or j.get("token")
                if access_token:
                    print("[AUTH SUCCESS] Acquired fisAccess token via " + str(url))
                    break
        except Exception as e:
            pass

    return access_token

def auto_discover_campaign_params(session, target_url, headers_json):
    discovered = {
        "campaign_id": None,
        "institution_id": None,
        "competitive_groups": {}
    }

    camp_id = os.getenv("FIS_CAMPAIGN_ID")
    if not camp_id:
        print("[ERROR] FIS_CAMPAIGN_ID is not configured in environment!")
        return discovered

    discovered["campaign_id"] = str(camp_id).strip()
    c_id_int = int(discovered["campaign_id"])

    env_inst_id = os.getenv("FIS_INSTITUTION_ID")
    if env_inst_id:
        try:
            discovered["institution_id"] = int(env_inst_id)
        except ValueError:
            pass

    if not discovered["institution_id"]:
        try:
            r_camp = session.post(target_url + "/Application/GetCampaignById", json={"campaignId": str(c_id_int)}, headers=headers_json, timeout=10)
            if r_camp.status_code == 200 and r_camp.text.startswith('{'):
                j_camp = r_camp.json()
                data_camp = j_camp.get("Data") or {}
                inst_id = data_camp.get("InstitutionID") or data_camp.get("InstitutionId")
                if inst_id:
                    discovered["institution_id"] = int(inst_id)
                    print(f"[CONFIG] Discovered InstitutionID = {discovered['institution_id']} via GetCampaignById")
        except Exception as e:
            print(f"[WARNING] GetCampaignById failed: {e}")

    if not discovered["institution_id"]:
        print("[ERROR] InstitutionID is missing!")
        return discovered

    print(f"[CONFIG] Active CampaignID = {discovered['campaign_id']}, InstitutionID = {discovered['institution_id']}")

    try:
        payload_cg = {
            "CampaignID": c_id_int,
            "EducationLevelID": "17",
            "InstitutionID": int(discovered["institution_id"])
        }
        r_cg = session.post(target_url + "/CompetitiveGroup/GetCompetitiveGroupsByCampaign", json=payload_cg, headers=headers_json, timeout=10)
        if r_cg.status_code == 200 and r_cg.text.startswith('{'):
            j_cg = r_cg.json()
            cg_list = j_cg.get("Data") or []
            if isinstance(cg_list, list) and len(cg_list) > 0:
                dynamic_cg = {}
                for item in cg_list:
                    cg_id = str(item.get("ID") or item.get("CompetitiveGroupID") or "")
                    cg_name = item.get("Name") or ""
                    if cg_id and cg_name:
                        dynamic_cg[cg_name] = cg_id
                        dynamic_cg[cg_name.lower()] = cg_id

                        prefix = re.sub(r'[\d\-]+$', '', cg_name.lower()).rstrip("\u0437").strip()
                        if prefix and prefix not in dynamic_cg:
                            dynamic_cg[prefix] = cg_id
                            dynamic_cg[prefix.lower()] = cg_id

                discovered["competitive_groups"] = dynamic_cg
                print(f"[SUCCESS] Dynamically loaded {len(cg_list)} Competitive Groups from FIS GIA server.")
                for item in cg_list:
                    print("   - Server Group: " + str(item.get("Name")) + " -> ID: " + str(item.get("ID")))
            else:
                print(f"[ERROR] GetCompetitiveGroupsByCampaign returned no groups: {r_cg.text[:150]}")
        else:
            print(f"[ERROR] GetCompetitiveGroupsByCampaign failed (HTTP {r_cg.status_code}): {r_cg.text[:150]}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch competitive groups: {e}")

    try:
        payload_ai = {"campaignID": c_id_int}
        r3 = session.post(target_url + "/Application/GetAdmissionItemTypeByCampaign", json=payload_ai, headers=headers_json, timeout=10)
        if r3.status_code == 200:
            print("[SUCCESS] Admission Item Types retrieved.")
    except Exception as e:
        print("[WARNING] GetAdmissionItemTypeByCampaign failed: " + str(e))

    if not discovered.get("campaign_id") or not discovered.get("competitive_groups"):
        print("[ERROR] Dynamic discovery incomplete: Campaign ID or Competitive Groups could not be retrieved from FIS GIA server!")

    return discovered

def extract_numeric_suffix(name):
    m = re.search(r'\d+', str(name))
    return int(m.group(0)) if m else 0

def resolve_competitive_group_ids_with_names(spec_name, dynamic_cg_map):
    if not spec_name or not dynamic_cg_map:
        return [], []

    spec_lower = str(spec_name).strip().lower()

    target_prefixes = []
    for keywords, prefixes in SPECIALTY_PREFIX_MAP:
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

        pref_base_match = re.search(r'^[A-Z\u0410-\u044f\u0401\u0451]+', pref_clean)
        pref_base = pref_base_match.group(0) if pref_base_match else pref_clean

        for cg_name, cg_id in dynamic_cg_map.items():
            cg_clean = str(cg_name).upper().strip()

            cg_base_match = re.search(r'^[A-Z\u0410-\u044f\u0401\u0451]+', cg_clean)
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

def submit_single_application(s, target_url, headers_json, data, discovered_config):
    campaign_id = discovered_config.get("campaign_id")
    institution_id = discovered_config.get("institution_id")
    dynamic_cg_map = discovered_config.get("competitive_groups") or {}

    last_name = data.get("last_name", "")
    first_name = data.get("first_name", "")
    middle_name = data.get("middle_name", "")
    app_num = data.get("application_number", "")
    passport_series = data.get("passport_series", "")
    passport_number = data.get("passport_number", "")

    if not campaign_id or not dynamic_cg_map:
        err_msg = "Application Submission Failed! Dynamic discovery incomplete: missing CampaignID or Competitive Groups from FIS GIA server."
        print("\n[CRITICAL ERROR] " + err_msg)
        print("   -> Application #" + str(app_num) + " SKIPPED. NewWz0 was NOT called.")
        return {
            "application_number": app_num,
            "passport_series": passport_series,
            "passport_number": passport_number,
            "status": "ERROR_DISCOVERY_FAILED",
            "message": err_msg
        }

    reg_address = data.get("reg_address_full", "")
    region_id = get_region_id(reg_address)
    town_type_id = get_town_type_id(reg_address, region_id)

    full_fio = " ".join(filter(None, [last_name, first_name, middle_name]))
    print("\n-----------------------------------------------------------------")
    print("   PROCESSING APPLICATION FOR FIS GIA")
    print("   Campaign ID: " + str(campaign_id) + ", Institution ID: " + str(institution_id))
    print("   Application No: " + str(app_num))
    print("   Applicant Name: " + str(full_fio))
    print("   Region ID: " + str(region_id) + ", Town Type ID: " + str(town_type_id))
    print("-----------------------------------------------------------------")

    requested_specialties = data.get("selected_specialties", [])
    requested_count = len(requested_specialties)
    
    seen_cg_ids = set()
    priorities_list = []
    matched_specialties_count = 0
    unmatched_specialties = []

    print("[SPECIALTY MATCHING] Matching " + str(requested_count) + " requested specialty/specialities against server competitive groups...")
    for idx, spec in enumerate(requested_specialties, start=1):
        spec_name = spec.get("speciality_name", "") if isinstance(spec, dict) else str(spec)
        m_ids, m_names = resolve_competitive_group_ids_with_names(spec_name, dynamic_cg_map)
        
        if m_ids:
            matched_specialties_count += 1
            print("   [MATCH SUCCESS] Specialty '" + str(spec_name) + "' -> Server Group(s): " + str(m_names) + " (ID(s): " + str(m_ids) + ")")
            for cg_id in m_ids:
                if cg_id not in seen_cg_ids:
                    seen_cg_ids.add(cg_id)
                    is_budget = spec.get("regional_budget_study_type_check") if isinstance(spec, dict) else True
                    priorities_list.append({
                        "CompetitiveGroupId": str(cg_id),
                        "EducationFormId": "11",
                        "EducationSourceId": "14" if is_budget else "15",
                        "IsForSPOandVO": False
                    })
        else:
            unmatched_specialties.append(spec_name)
            print("   [MATCH FAILURE] Could NOT match specialty: '" + str(spec_name) + "'!")

    if len(priorities_list) == 0:
        err_msg = f"Specialty Matching Failed! 0 of {requested_count} requested specialties matched valid competitive groups in FIS GIA."
        print("\n[CRITICAL ERROR] " + err_msg)
        print("   -> Application #" + str(app_num) + " SKIPPED. NewWz0 was NOT called.")
        return {
            "application_number": app_num,
            "passport_series": passport_series,
            "passport_number": passport_number,
            "status": "ERROR_UNMATCHED_SPECIALTY",
            "message": err_msg
        }

    is_partial_success = (matched_specialties_count < requested_count)
    if is_partial_success:
        print(f"\n[SPECIALTY MATCHING WARNING] Partial match: {matched_specialties_count} of {requested_count} specialties matched. Unmatched: {unmatched_specialties}")

    selected_cg_ids = [p["CompetitiveGroupId"] for p in priorities_list]

    wz0_payload = {
        "ApplicationId": 0,
        "InstitutionID": int(institution_id),
        "CampaignID": str(campaign_id),
        "DocumentSeries": passport_series,
        "DocumentNumber": passport_number,
        "FromEPGU": True,
        "IdentityDocumentTypeID": "1",
        "RegistrationDate": data.get("registration_date") or os.getenv("REGISTRATION_DATE") or DEFAULT_SETTINGS["registration_date"],
        "ApplicationNumber": str(app_num),
        "Priorities": {
            "ApplicationId": -1,
            "ApplicationPriorities": priorities_list
        },
        "SelectedCompetitiveGroupIDs": [],
        "SelectedDirectionIDs": [],
        "SelectedParentDirectionIDs": None,
        "SelectedTargetOrganizationIDO": 0,
        "SelectedTargetOrganizationIDOZ": 0,
        "SelectedTargetOrganizationIDZ": 0,
        "CheckForExistingBeforeCreate": True,
        "CheckUniqueBeforeCreate": True,
        "CheckZerozBeforeCreate": True,
        "After11": False
    }

    # STEP 1: NewWz0
    print("[STEP 1] Initializing application (NewWz0)...")
    r0 = s.post(target_url + "/Application/NewWz0", json=wz0_payload, headers=headers_json)
    if r0.status_code != 200 or not r0.text.strip():
        err_msg = f"NewWz0 HTTP error {r0.status_code}: {r0.text[:300]}"
        print("[ERROR] " + err_msg)
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    try:
        j0 = r0.json()
    except Exception:
        err_msg = f"NewWz0 returned non-JSON response (HTTP {r0.status_code}): {r0.text[:300]}"
        print("[ERROR] " + err_msg)
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    if j0.get("IsError"):
        err_msg = str(j0.get("Message") or "Error in NewWz0")
        print("[NEWWZ0 RESPONSE ERROR] " + err_msg)
        is_num_in_use = ("\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f" in err_msg.lower() or "\u043d\u043e\u043c\u0435\u0440" in err_msg.lower() or "already" in err_msg.lower())
        status_code = "ERROR_APP_NUMBER_EXISTS" if is_num_in_use else "ERROR"
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": status_code, "message": err_msg}

    data0 = j0.get("Data") if isinstance(j0.get("Data"), dict) else j0
    app_id = extract_id(data0, "ApplicationID", "ApplicationId", "id") or extract_id(j0, "ApplicationID", "ApplicationId", "id")

    entrant_is_new = data0.get("EntrantIsNew") if isinstance(data0, dict) else j0.get("EntrantIsNew")

    if not app_id or app_id == 0 or entrant_is_new is False:
        has_existing_app = False
        existing_app_info = None

        if passport_series and passport_number:
            print(f"[CHECK EXISTING APP] EntrantIsNew = False for passport {passport_series} {passport_number}. Querying LoadApplicationNewRecords...")
            search_payload = {
                "Filter": {
                    "ApplicationNumber": "",
                    "OriginalDocumentsReceived": None,
                    "LastName": "",
                    "FirstName": None,
                    "MiddleName": None,
                    "SelectedViolationType": None,
                    "Order": None,
                    "RegistrationDateFrom": None,
                    "RegistrationDateTo": None,
                    "SelectedCompetitiveGroup": None,
                    "DocumentSeries": str(passport_series),
                    "DocumentNumber": str(passport_number),
                    "UID": None,
                    "CampaignYear": datetime.now().year,
                    "SelectedBenefitId": 0,
                    "SelectedCampaignId": int(campaign_id) if (campaign_id and str(campaign_id).isdigit()) else None,
                    "SelectedEducationFormType": None,
                    "SelectedEducationSourceType": None,
                    "SNILS": None
                },
                "Pager": {
                    "PageSize": 10,
                    "CurrentPage": 1,
                    "TotalRecords": 1,
                    "TotalPages": 1,
                    "FirstRecordOffset": 1,
                    "LastRecordOffset": 10
                },
                "Sort": {
                    "SortDescending": True,
                    "SortKey": "RegistrationDate"
                }
            }

            try:
                r_search = s.post(target_url + "/InstitutionApplication/LoadApplicationNewRecords", json=search_payload, headers=headers_json)
                if r_search.status_code == 200:
                    j_search = r_search.json()
                    records = j_search.get("Records", []) if isinstance(j_search, dict) else []
                    if records and len(records) > 0:
                        for rec in records:
                            rec_eid = rec.get("EntrantId") or rec.get("EntrantID")
                            if rec_eid and int(rec_eid) > 0 and not entrant_id:
                                entrant_id = int(rec_eid)

                            found_app_id = rec.get("ApplicationId") or rec.get("ApplicationID")
                            if found_app_id and int(found_app_id) > 0 and int(found_app_id) != int(app_id):
                                has_existing_app = True
                                existing_app_info = rec
                                break
            except Exception as search_err:
                print(f"   [WARNING] Failed to query LoadApplicationNewRecords: {search_err}")

        if has_existing_app:
            existing_num = existing_app_info.get("ApplicationNumber") if existing_app_info else "N/A"
            existing_id = existing_app_info.get("ApplicationId") if existing_app_info else "N/A"
            msg = f"Entrant already has an application in FIS GIA (Application #{existing_num}, ID {existing_id})"
            print(f"[ALREADY EXISTS] {msg}. Deleting draft application {app_id}...")
            if app_id and int(app_id) > 0:
                try:
                    del_res = s.post(target_url + "/InstitutionApplication/DeleteApplications", json={"applicationId": [int(app_id)]}, headers=headers_json)
                    print(f"   [DELETED DRAFT] Deleted draft ApplicationID {app_id} (HTTP {del_res.status_code}: {del_res.text[:150]})")
                except Exception as del_err:
                    print(f"   [WARNING] Failed to delete draft ApplicationID {app_id}: {del_err}")

            return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ALREADY_EXISTS", "message": msg}

        print(f"[NEW APPLICATION FOR EXISTING ENTRANT] EntrantIsNew = False, but NO OTHER application found for passport {passport_series} {passport_number}. Continuing submission with draft ApplicationID {app_id}...")

    print("[SUCCESS] Step 1 created ApplicationID: " + str(app_id))

    # STEP 1.5: Discover EntrantID
    entrant_id, passport_doc_id = get_entrant_id_from_server(s, target_url, headers_json, app_id, j0)

    if entrant_id:
        print("   [INFO] Discovered EntrantID: " + str(entrant_id))
    else:
        print("   [WARNING] Could NOT extract EntrantID for ApplicationID " + str(app_id))

    # STEP 2: UpdWz1
    reg_date = data.get("registration_date") or os.getenv("REGISTRATION_DATE") or DEFAULT_SETTINGS["registration_date"]
    upd_wz1_payload = {
        "ApplicationID": int(app_id),
        "InstitutionID": int(institution_id),
        "EntrantID": str(entrant_id) if entrant_id else "",
        "LastName": last_name,
        "FirstName": first_name,
        "MiddleName": middle_name,
        "SNILS": data.get("snils", ""),
        "GenderID": "1" if data.get("gender") == "\u041c\u0443\u0436\u0441\u043a\u043e\u0439" else "2",
        "BirthDate": data.get("date_of_birth", "01.01.2000"),
        "DocumentTypeID": "1",
        "DocumentSeries": passport_series,
        "DocumentNumber": passport_number,
        "DocumentOrganization": data.get("passport_organization", ""),
        "DocumentDate": data.get("passport_date", "01.01.2020"),
        "SubdivisionCode": data.get("passport_issuer_code", ""),
        "NationalityID": "1",
        "BirthPlace": "",
        "CustomInformation": "",
        "ReleaseCountryID": "1",
        "ReleasePlace": "\u0420\u043e\u0441\u0441\u0438\u044f",
        "SelectedCitizenships": None,
        "NoSnilsReason": "0",
        "Email": data.get("email", ""),
        "RegionID": region_id,
        "TownTypeID": town_type_id,
        "Address": reg_address,
        "IsFromKrym": False,
        "IsFromKrymEntrantDocumentID": "",
        "FromEPGU": True,
        "IsFromEPGU": True,
        "OriginalReceived": True,
        "OriginalReceivedDate": str(reg_date),
        "IsOriginal": True,
        "IsCopy": False,
        "WizardStepID": 2
    }

    r1 = s.post(target_url + "/Application/UpdWz1", json=upd_wz1_payload, headers=headers_json)
    if r1.status_code != 200 or not r1.text.strip():
        err_msg = f"UpdWz1 HTTP {r1.status_code}: {r1.text[:300]}"
        print(f"[ERROR] Step 2 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    try:
        j1 = r1.json()
    except Exception:
        err_msg = f"UpdWz1 returned invalid JSON (HTTP {r1.status_code}): {r1.text[:300]}"
        print(f"[ERROR] Step 2 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    if j1.get("IsError"):
        err_msg = f"UpdWz1 error: {j1.get('Message') or j1}"
        print(f"[ERROR] Step 2 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    updated_entrant_id = extract_id(j1.get("Data"), "EntrantID", "EntrantId", "id") or extract_id(j1, "EntrantID", "EntrantId", "id")
    if updated_entrant_id:
        entrant_id = updated_entrant_id

    if not passport_doc_id:
        passport_doc_id = extract_id(j1.get("Data"), "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID") or extract_id(j1, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID")
    print("[SUCCESS] Step 2 updated personal details. EntrantID: " + str(entrant_id))

    if not entrant_id or int(entrant_id) == 0:
        err_msg = f"Cannot proceed to Step 3 for ApplicationID {app_id}: missing valid EntrantID from FIS GIA server."
        print(f"[ERROR] Step 3 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    # STEP 3: Attach Education Document via /Entrant/setEditDocument
    raw_gpa = data.get("average_mark")
    gpa_str = format_gpa(raw_gpa)
    doc_series_edu = str(data.get("diploma_series", "")).strip()
    if doc_series_edu == "-":
        doc_series_edu = ""

    doc_org_edu = str(data.get("diploma_organization") or data.get("prev_unit") or "")

    edu_payload = {
        "EntrantID": int(entrant_id) if entrant_id else 0,
        "EntrantDocumentID": 0,
        "DocumentTypeID": 16,
        "DocumentTypeName": "",
        "UID": "",
        "ApplicationID": int(app_id),
        "DocumentSeries": doc_series_edu,
        "DocumentNumber": str(data.get("diploma_number", "")),
        "DocumentDate": str(data.get("diploma_date", "")),
        "DocumentOrganization": doc_org_edu,
        "OriginalReceived": True,
        "OriginalReceivedDate": str(reg_date),
        "EntDocEdu": {
            "GPA": gpa_str,
            "RegionId": str(region_id),
            "StateServicePreparation": False,
            "IsNostrificated": False
        },
        "EntDocSubBall": {
            "SubjectBalls": []
        }
    }

    try:
        s.post(target_url + "/Entrant/checkExistEnt", json=edu_payload, headers=headers_json, timeout=10)
    except Exception:
        pass

    r3 = s.post(target_url + "/Entrant/setEditDocument", json=edu_payload, headers=headers_json)
    if r3.status_code != 200 or not r3.text.strip():
        err_msg = f"setEditDocument HTTP {r3.status_code}: {r3.text[:300]}"
        print(f"[ERROR] Step 3 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    try:
        j3 = r3.json()
    except Exception:
        err_msg = f"setEditDocument returned invalid JSON (HTTP {r3.status_code}): {r3.text[:300]}"
        print(f"[ERROR] Step 3 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    if j3.get("IsError"):
        err_msg = f"setEditDocument error: {j3.get('Message') or j3}"
        print(f"[ERROR] Step 3 failed: {err_msg}")
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    edu_doc_id = extract_id(j3.get("Data"), "id", "EntrantDocumentID", "EntrantDocumentId") or extract_id(j3, "id", "EntrantDocumentID", "EntrantDocumentId")
    print("[SUCCESS] Step 3 attached Education Document ID: " + str(edu_doc_id))

    # Confirm original documents received (1. Passport, 2. Attestat)
    headers_form = dict(headers_json)
    headers_form["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers_form["Referer"] = target_url + "/Application/Edit/" + str(app_id)

    if not passport_doc_id:
        passport_doc_id = get_passport_doc_id(s, target_url, headers_json, app_id, edu_doc_id, entrant_id=entrant_id, j0=j0, j1=j1)

    # 1. Confirm Passport Original
    if passport_doc_id:
        print("[SUCCESS] Confirming original Passport document ID: " + str(passport_doc_id))
        form_pass = f"applicationID={app_id}&entrantDocumentID={passport_doc_id}&received=true&receivedDate={reg_date}"
        s.post(target_url + "/Application/SetDocumentOriginalReceived", data=form_pass, headers=headers_form)

    # 2. Confirm Education Original
    if edu_doc_id:
        print("[SUCCESS] Confirming original Education document ID: " + str(edu_doc_id))
        form_edu = f"applicationID={app_id}&entrantDocumentID={edu_doc_id}&received=true&receivedDate={reg_date}"
        s.post(target_url + "/Application/SetDocumentOriginalReceived", data=form_edu, headers=headers_form)

    # STEP 4: SaveWz5
    print("\n[STEP 4] Executing /Application/SaveWz5 ...")
    priorities_wz5 = []
    for item in priorities_list:
        p_item = dict(item)
        p_item["ApplicationId"] = int(app_id)
        p_item["IsAgreed"] = False
        p_item["IsDisagreed"] = False
        p_item["IsDisagreedDate"] = ""
        p_item["CalculatedRating"] = ""
        priorities_wz5.append(p_item)

    wz5_payload = {
        "model": {
            "Step": 4,
            "ApplicationID": int(app_id),
            "EntrantID": int(entrant_id) if entrant_id else 0,
            "RegistrationDate": str(reg_date),
            "ApplicationNumber": str(app_num),
            "NeedHostel": False,
            "changePage": False,
            "FromEPGU": True,
            "IsFromEPGU": True,
            "ApplicationPriorities": {
                "ApplicationId": int(app_id),
                "ApplicationPriorities": priorities_wz5,
                "ChangeCg": False
            },
            "After11": False
        }
    }
    res5 = s.post(target_url + "/Application/SaveWz5", json=wz5_payload, headers=headers_json)
    print(f"[DEBUG] Step 4 SaveWz5 HTTP Status: {res5.status_code}, Response: {res5.text[:200]}")

    if is_partial_success:
        final_status = "PARTIAL_SUCCESS"
        final_msg = f"Application registered with PARTIAL SUCCESS (matched {matched_specialties_count} of {requested_count} competitive groups). Unmatched: {unmatched_specialties}"
    else:
        final_status = "CREATED"
        final_msg = f"Application registered successfully in FIS GIA with ID {app_id}"

    print(f"\n[APPLICATION {final_status}] Application {app_num}: {final_msg}")
    return {
        "application_number": str(app_num),
        "passport_series": str(passport_series),
        "passport_number": str(passport_number),
        "status": final_status,
        "message": final_msg,
        "fis_application_id": app_id,
        "matched_groups_count": matched_specialties_count,
        "total_requested_count": requested_count,
        "unmatched_specialties": unmatched_specialties
    }

class TeeLogger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log_file = open(filepath, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()

def run_fis_submission(json_file=None):
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    server_dir = os.path.dirname(os.path.abspath(__file__))

    logs_dir = os.path.join(server_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_filename = os.path.join(logs_dir, f"log_{now_str}.txt")
    response_filename = os.path.join(logs_dir, f"response_{now_str}.json")

    tee_logger = TeeLogger(log_filename)
    sys.stdout = tee_logger

    global SPECIALTY_PREFIX_MAP
    SPECIALTY_PREFIX_MAP = load_specialty_prefix_map()

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
        with open(json_file, "rb") as f:
            content = f.read()
        try:
            raw_input = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_input = json.loads(content.decode("cp1251"))
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

    # Dynamic Warmup Discovery (with automatic fallback)
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

if __name__ == "__main__":
    filepath = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and arg.lower() not in ["dev", "prod"]:
            if arg.endswith(".json") or os.path.exists(arg):
                filepath = arg
                break
    run_fis_submission(filepath)
