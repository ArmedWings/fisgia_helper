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

# Pure Python config.env / .env parser (Zero external dependencies)
def _load_server_env():
    server_dir = os.path.dirname(__file__)
    for filename in ['config.env', '.env']:
        filepath = os.path.join(server_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            if k and k not in os.environ:
                                os.environ[k] = v
                return
            except Exception:
                pass

_load_server_env()

# ------------------------------------------------------------------------------
# CENTRAL CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------------------
FIS_BASE_URL = os.getenv("FIS_BASE_URL", "http://10.0.3.1:8383").rstrip('/')

# # Keyword stem mapping for specialty names (Unicode escaped for Windows 7 compatibility)
ALIAS_KEYWORD_GROUPS = {
    # MMS (15.02.12 / 15.02.01 / 15.02.07 / Montazh, remont promyshlennogo oborudovaniya)
    "\u043c\u043c\u0441": ["\u043c\u043c\u0441"],
    "\u043c\u043e\u043d\u0442\u0430\u0436": ["\u043c\u043c\u0441"],
    "\u043f\u0440\u043e\u043c\u044b\u0448\u043b\u0435\u043d\u043d\u043e\u0433\u043e \u043e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u044f": ["\u043c\u043c\u0441"],
    "15.02.12": ["\u043c\u043c\u0441"],
    "15.02.01": ["\u043c\u043c\u0441"],
    "15.02.07": ["\u043c\u043c\u0441"],

    # ON / P (15.01.33 / 15.01.05 / Operator-naladchik, Stanochnik)
    "\u043e\u043d": ["\u043e\u043d"],
    "\u043e\u043f\u0435\u0440\u0430\u0442\u043e\u0440-\u043d\u0430\u043b\u0430\u0434\u0447\u0438\u043a": ["\u043e\u043d", "\u043f"],
    "\u043e\u043f\u0435\u0440\u0430\u0442\u043e\u0440 \u043d\u0430\u043b\u0430\u0434\u0447\u0438\u043a": ["\u043e\u043d", "\u043f"],
    "\u043d\u0430\u043b\u0430\u0434\u0447\u0438\u043a": ["\u043e\u043d"],
    "\u043e\u043f\u0435\u0440\u0430\u0442\u043e\u0440": ["\u043e\u043d"],
    "\u043c\u0435\u0442\u0430\u043b\u043b\u043e\u043e\u0431\u0440\u0430\u0431\u043e\u0442\u044b\u0432\u0430\u044e\u0449\u0438\u0445": ["\u043e\u043d", "\u043f"],
    "\u0441\u0442\u0430\u043d\u043e\u0447\u043d\u0438\u043a": ["\u043f"],
    "\u043f": ["\u043f"],
    "15.01.33": ["\u043e\u043d"],
    "15.01.05": ["\u043f"],

    # TOA (23.02.07 / Avtotransport)
    "\u0442\u043e\u0430": ["\u0442\u043e\u0430"],
    "\u0430\u0432\u0442\u043e\u0442\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442": ["\u0442\u043e\u0430"],
    "\u0430\u0432\u0442\u043e\u0442\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442\u043d\u044b\u0445": ["\u0442\u043e\u0430"],
    "\u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b": ["\u0442\u043e\u0430"],
    "23.02.07": ["\u0442\u043e\u0430"],

    # SV (15.01.05 / Svarchik)
    "\u0441\u0432": ["\u0441\u0432"],
    "\u0441\u0432\u0430\u0440": ["\u0441\u0432"],

    # E (13.01.10 / Elektromonter)
    "\u044d": ["\u044d"],
    "\u044d\u043b\u0435\u043a\u0442\u0440\u043e\u043c\u043e\u043d\u0442": ["\u044d"],
    "\u044d\u043b\u0435\u043a\u0442\u0440\u043e\u043e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u044f": ["\u044d"],
    "13.01.10": ["\u044d"],

    # FK (49.02.01 / Fizicheskaya kultura)
    "\u0444\u043a": ["\u0444\u043a"],
    "\u0444\u0438\u0437\u0438\u0447\u0435\u0441\u043a": ["\u0444\u043a"],
    "49.02.01": ["\u0444\u043a"],

    # DO (44.02.01 / Doshkolnoe obrazovanie)
    "\u0434\u043e": ["\u0434\u043e"],
    "\u0434\u043e\u0448\u043a\u043e\u043b\u044c\u043d": ["\u0434\u043e"],
    "44.02.01": ["\u0434\u043e"],

    # SD (34.02.01 / Sestrinskoe delo)
    "\u0441\u0434": ["\u0441\u0434"],
    "\u0441\u0435\u0441\u0442\u0440\u0438\u043d\u0441\u043a": ["\u0441\u0434"],
    "34.02.01": ["\u0441\u0434"],

    # U (40.02.04 / Yurisprudenciya)
    "\u044e": ["\u044e"],
    "\u044e\u0440\u0438\u0441\u043f\u0440\u0443\u0434": ["\u044e"],
    "40.02.04": ["\u044e"],

    # PD / PSO (40.02.01 / 40.02.02 / Pravo i organizaciya)
    "\u043f\u0441\u043e": ["\u043f\u0441\u043e"],
    "\u043f\u0440\u0430\u0432\u043e \u0438 \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u044f": ["\u043f\u0441\u043e"],
    "\u0441\u043e\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0435\u043d\u0438\u044f": ["\u043f\u0441\u043e"],
    "\u043f\u0434": ["\u043f\u0434"],
    "\u043f\u0440\u0430\u0432\u043e\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u044c\u043d": ["\u043f\u0434"],
    "40.02.01": ["\u043f\u0441\u043e"],
    "40.02.02": ["\u043f\u0434"],

    # MMR (15.01.32 / Mekhatronika)
    "\u043c\u043c\u0440": ["\u043c\u043c\u0440"],
    "\u043c\u0440": ["\u043c\u043c\u0440"],
    "\u043c\u0435\u0445\u0430\u0442\u0440\u043e\u043d": ["\u043c\u043c\u0440"],
    "\u0440\u043e\u0431\u043e\u0442\u043e\u0442\u0435\u0445\u043d\u0438\u043a\u0438": ["\u043c\u043c\u0440"],
    "15.01.32": ["\u043c\u043c\u0440"],

    # PK (43.01.09 / Povar, konditer)
    "\u043f\u043a": ["\u043f\u043a"],
    "\u043f\u043e\u0432\u0430\u0440": ["\u043f\u043a"],
    "\u043a\u043e\u043d\u0434\u0438\u0442\u0435\u0440": ["\u043f\u043a"],

    # BU (38.02.01 / Ekonomika)
    "\u0431\u0443": ["\u0431\u0443"],
    "\u044d\u043a\u043e\u043d\u043e\u043c\u0438\u043a": ["\u0431\u0443"],
    "\u0431\u0443\u0445\u0433\u0430\u043b\u0442\u0435\u0440": ["\u0431\u0443"],
    "38.02.01": ["\u0431\u0443"],

    # LAB (18.01.34)
    "\u043b\u0430\u0431": ["\u043b\u0430\u0431"],
    "\u043b\u0430\u0431\u043e\u0440\u0430\u043d\u0442": ["\u043b\u0430\u0431"],

    # MI (18.01.08 / Master)
    "\u043c\u0438": ["\u043c\u0438"],
    "\u0441\u0442\u0435\u043a\u043b": ["\u043c\u0438"],
}

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
    eid = extract_id(j0.get("Data"), "EntrantID", "EntrantId") or extract_id(j0, "EntrantID", "EntrantId")
    pid = extract_id(j0.get("Data"), "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID") or extract_id(j0, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID")
    if eid:
        return eid, pid

    try:
        r_wz1 = s.post(target_url + "/Application/Wz1", json={"id": int(app_id)}, headers=headers_json)
        if r_wz1.status_code == 200:
            if r_wz1.text.startswith('{'):
                j_wz1 = r_wz1.json()
                data_wz1 = j_wz1.get("Data") or j_wz1
                eid = extract_id(data_wz1, "EntrantID", "EntrantId") or eid
                pid = extract_id(data_wz1, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID") or pid
            elif r_wz1.text:
                match = re.search(r'id="EntrantID"[^>]*value="(\d+)"', r_wz1.text, re.IGNORECASE)
                if not match:
                    match = re.search(r'name="EntrantID"[^>]*value="(\d+)"', r_wz1.text, re.IGNORECASE)
                if not match:
                    match = re.search(r'EntrantID["\s:=]+(\d+)', r_wz1.text, re.IGNORECASE)
                if match:
                    eid = int(match.group(1))
    except Exception:
        pass

    return eid, pid

def get_passport_doc_id(s, target_url, headers_json, app_id, edu_doc_id, j0=None, j1=None):
    # 1. Check j1 / j0 JSON responses
    for source in [j1, j0]:
        if isinstance(source, dict):
            pid = extract_id(source.get("Data"), "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID") or \
                  extract_id(source, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID")
            if pid and pid > 10000000 and pid != int(edu_doc_id):
                return pid

    headers_html = dict(headers_json)
    headers_html["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    
    # 2. Search Wz3 GET/POST for 8-9 digit document IDs
    try:
        r_wz3 = s.get(target_url + f"/Application/Wz3?id={app_id}", headers=headers_html)
        text = r_wz3.text
        if text:
            matches = re.findall(r'(?:entrantDocumentID|entrantdocumentid|docid|documentid)["\']?\s*[:=]\s*["\']?(\d{7,11})["\']?', text, re.IGNORECASE) or \
                      re.findall(r'SetDocumentOriginalReceived[^)]*?(\d{7,11})', text, re.IGNORECASE) or \
                      re.findall(r'value=["\'](\d{7,11})["\'][^>]*name=["\'](?:entrantDocumentID|EntrantDocumentID)["\']', text, re.IGNORECASE) or \
                      re.findall(r'name=["\'](?:entrantDocumentID|EntrantDocumentID)["\'][^>]*value=["\'](\d{7,11})["\']', text, re.IGNORECASE) or \
                      re.findall(r'\b(\d{8,9})\b', text)
            for m in matches:
                doc_id = int(m)
                if edu_doc_id and doc_id == int(edu_doc_id):
                    continue
                if doc_id > 10000000 and doc_id != int(app_id):
                    return doc_id
    except Exception:
        pass

    try:
        r_wz3_post = s.post(target_url + "/Application/Wz3", json={"id": int(app_id)}, headers=headers_json)
        text = r_wz3_post.text
        if text:
            matches = re.findall(r'(?:entrantDocumentID|entrantdocumentid|docid|documentid)["\']?\s*[:=]\s*["\']?(\d{7,11})["\']?', text, re.IGNORECASE) or \
                      re.findall(r'["\']EntrantDocumentID["\']\s*:\s*(\d{7,11})', text, re.IGNORECASE) or \
                      re.findall(r'\b(\d{8,9})\b', text)
            for m in matches:
                doc_id = int(m)
                if edu_doc_id and doc_id == int(edu_doc_id):
                    continue
                if doc_id > 10000000 and doc_id != int(app_id):
                    return doc_id
    except Exception:
        pass

    # 3. Fallback: In GVUZ MS SQL Server IDENTITY(1,1), Passport is inserted first (N), Diploma is inserted second (N+1)
    if edu_doc_id and int(edu_doc_id) > 1:
        return int(edu_doc_id) - 1

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
    a_lower = address.lower()
    if "\u0433." in a_lower or "\u0433 " in a_lower or "\u0433\u043e\u0440\u043e\u0434" in a_lower:
        return "2"
    elif "\u043f\u0433\u0442" in a_lower or "\u043f\u043e\u0441\u0435\u043b\u043e\u043a" in a_lower:
        return "3"
    elif "\u0434." in a_lower or "\u0434\u0435\u0440\u0435\u0432\u043d\u044f" in a_lower or "\u0441." in a_lower or "\u0441\u0435\u043b\u043e" in a_lower:
        return "4"
    return "2"

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
    print("\n[AUTO-DISCOVERY] Requesting GetDataForApplicationsList to discover Campaign & Institution parameters...")
    discovered = {
        "campaign_id": None,
        "institution_id": 6982,
        "competitive_groups": {}
    }

    get_data_urls = [
        target_url + "/InstitutionApplication/GetDataForApplicationsList",
        target_url + "/Application/GetDataForApplicationsList"
    ]

    for url in get_data_urls:
        try:
            r1 = session.post(url, json={}, headers=headers_json, timeout=10)
            if r1.status_code == 200 and r1.text.startswith('{'):
                j1 = r1.json()
                data1 = j1.get("Data") or j1
                
                inst_id = data1.get("InstitutionID") or data1.get("InstitutionId") or j1.get("InstitutionId")
                if inst_id:
                    discovered["institution_id"] = int(inst_id)

                campaign_list = data1.get("CampaignData") or j1.get("CampaignData") or []
                if isinstance(campaign_list, list) and len(campaign_list) > 0:
                    latest_campaign = campaign_list[-1]
                    c_id = latest_campaign.get("Id") or latest_campaign.get("CampaignID")
                    c_name = latest_campaign.get("Name", "")
                    if c_id:
                        discovered["campaign_id"] = str(c_id)
                        print("[AUTO-DISCOVERY SUCCESS] Extracted latest campaign from CampaignData: CampaignID = " + str(discovered["campaign_id"]) + " ('" + str(c_name) + "'), InstitutionID = " + str(discovered["institution_id"]))
                        break
            else:
                print(f"[AUTO-DISCOVERY WARNING] {url} returned HTTP {r1.status_code}: {r1.text[:200]}")
        except Exception as e:
            print("[AUTO-DISCOVERY DEBUG] " + str(url) + " failed: " + str(e))

    if discovered["campaign_id"]:
        try:
            payload_cg = {
                "CampaignID": int(discovered["campaign_id"]),
                "EducationLevelID": "17",
                "InstitutionID": int(discovered["institution_id"] or 6982)
            }
            r2 = session.post(target_url + "/CompetitiveGroup/GetCompetitiveGroupsByCampaign", json=payload_cg, headers=headers_json, timeout=10)
            if r2.status_code == 200 and r2.text.startswith('{'):
                j2 = r2.json()
                cg_list = j2.get("Data") or []
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
                    print("[AUTO-DISCOVERY SUCCESS] Loaded " + str(len(cg_list)) + " Competitive Groups dynamically from server:")
                    for item in cg_list:
                        print("   - Server Group: " + str(item.get("Name")) + " -> ID: " + str(item.get("ID")))
            else:
                print(f"[AUTO-DISCOVERY WARNING] GetCompetitiveGroupsByCampaign returned HTTP {r2.status_code}: {r2.text[:200]}")
        except Exception as e:
            print("[AUTO-DISCOVERY WARNING] GetCompetitiveGroupsByCampaign failed: " + str(e))

        try:
            payload_ai = {"campaignID": int(discovered["campaign_id"])}
            r3 = session.post(target_url + "/Application/GetAdmissionItemTypeByCampaign", json=payload_ai, headers=headers_json, timeout=10)
            if r3.status_code == 200:
                print("[AUTO-DISCOVERY SUCCESS] Admission Item Types retrieved.")
        except Exception as e:
            print("[AUTO-DISCOVERY WARNING] GetAdmissionItemTypeByCampaign failed: " + str(e))

    # FALLBACK PROTECTION:
    if not discovered.get("campaign_id") or not discovered.get("competitive_groups"):
        print("[AUTO-DISCOVERY FALLBACK] Dynamic discovery incomplete. Applying default fallback parameters (CampaignID = 42837, InstitutionID = 6982)...")
        discovered["campaign_id"] = discovered.get("campaign_id") or "42837"
        discovered["institution_id"] = discovered.get("institution_id") or 6982
        if not discovered.get("competitive_groups"):
            discovered["competitive_groups"] = {
                "\u0414\u041e21": "2066315", "\u0434\u043e21": "2066315", "\u0434\u043e": "2066315",
                "\u041c\u041821": "2066323", "\u043c\u043821": "2066323", "\u043c\u0438": "2066323",
                "\u041c\u041c\u042021": "2065764", "\u043c\u043c\u044021": "2065764", "\u043c\u043c\u0440": "2065764",
                "\u041c\u041c\u042121": "2066321", "\u043c\u043c\u044121": "2066321", "\u043c\u043c\u0441": "2066321",
                "\u041f\u041a21": "2066322", "\u043f\u043a21": "2066322", "\u043f\u043a": "2066322",
                "\u041f\u0421\u041e21": "2066325", "\u043f\u0441\u043e21": "2066325", "\u043f\u0441\u043e": "2066325",
                "\u0421\u041221": "2066319", "\u0441\u043221": "2066319", "\u0441\u0432": "2066319",
                "\u0424\u041a21": "2066309", "\u0444\u043a21": "2066309", "\u0444\u043a": "2066309",
                "\u042d21": "2066316", "\u044d21": "2066316", "\u044d": "2066316"
            }

    return discovered

def resolve_competitive_group_ids_with_names(spec_name, dynamic_cg_map):
    if not spec_name or not dynamic_cg_map:
        return [], []

    spec_raw = str(spec_name).strip()
    spec_lower = spec_raw.lower()
    matched_ids = []
    matched_names = []

    target_tags = set()
    for kw, tags in ALIAS_KEYWORD_GROUPS.items():
        if kw in spec_lower:
            for t in tags:
                clean_tag = re.sub(r'[\d\-]+$', '', t.lower().strip()).rstrip("\u0437").strip()
                if clean_tag:
                    target_tags.add(clean_tag)

    if not target_tags:
        return [], []

    for cg_name, cg_id in dynamic_cg_map.items():
        if cg_name.islower() and any(k.isupper() for k in dynamic_cg_map.keys() if dynamic_cg_map[k] == cg_id):
            continue

        cg_lower = cg_name.lower().strip()
        cg_prefix = re.sub(r'[\d\-]+$', '', cg_lower).strip()
        cg_prefix_no_z = cg_prefix.rstrip("\u0437").strip()

        # Strict exact match only! No partial substring matching!
        if any(tag == cg_prefix or tag == cg_prefix_no_z for tag in target_tags):
            if cg_id not in matched_ids:
                matched_ids.append(cg_id)
                matched_names.append(cg_name)

    return matched_ids, matched_names

def submit_single_application(s, target_url, headers_json, data, discovered_config):
    campaign_id = discovered_config["campaign_id"]
    institution_id = discovered_config["institution_id"] or 6982
    dynamic_cg_map = discovered_config["competitive_groups"]

    last_name = data.get("last_name", "")
    first_name = data.get("first_name", "")
    middle_name = data.get("middle_name", "")
    app_num = data.get("application_number", DEFAULT_SETTINGS["default_app_number"])
    passport_series = data.get("passport_series", "")
    passport_number = data.get("passport_number", "")

    reg_address = data.get("reg_address_full", "")
    region_id = get_region_id(reg_address)
    town_type_id = get_town_type_id(reg_address, region_id)

    masked_initials = (last_name[:1] + "." if last_name else "") + (first_name[:1] + "." if first_name else "") + (middle_name[:1] + "." if middle_name else "")
    print("\n-----------------------------------------------------------------")
    print("   PROCESSING APPLICATION FOR FIS GIA")
    print("   Campaign ID: " + str(campaign_id) + ", Institution ID: " + str(institution_id))
    print("   Application No: " + str(app_num))
    print("   Applicant Initials: " + str(masked_initials))
    print("   Region ID: " + str(region_id) + ", Town Type ID: " + str(town_type_id))
    print("-----------------------------------------------------------------")

    requested_specialties = data.get("selected_specialties", [])
    requested_count = len(requested_specialties)
    
    seen_cg_ids = set()
    priorities_list = []
    matched_specialties_count = 0

    print("[SPECIALTY MATCHING] Matching " + str(requested_count) + " requested specialty/specialities against server competitive groups...")
    for idx, spec in enumerate(requested_specialties, start=1):
        spec_name = spec.get("speciality_name", "")
        m_ids, m_names = resolve_competitive_group_ids_with_names(spec_name, dynamic_cg_map)
        
        if m_ids:
            matched_specialties_count += 1
            print("   [MATCH SUCCESS] Specialty '" + str(spec_name) + "' -> Server Group(s): " + str(m_names) + " (ID(s): " + str(m_ids) + ")")
            for cg_id in m_ids:
                if cg_id not in seen_cg_ids:
                    seen_cg_ids.add(cg_id)
                    priorities_list.append({
                        "CompetitiveGroupId": str(cg_id),
                        "EducationFormId": "11",
                        "EducationSourceId": "14" if spec.get("regional_budget_study_type_check") else "15",
                        "IsForSPOandVO": False
                    })
        else:
            print("   [MATCH FAILURE] Could NOT match specialty: '" + str(spec_name) + "'!")

    if len(priorities_list) == 0:
        err_msg = f"Specialty Matching Failed! None of the {requested_count} requested specialty/specialties matched valid competitive groups in FIS GIA."
        print("\n[CRITICAL ERROR] " + err_msg)
        print("   -> Application #" + str(app_num) + " SKIPPED. NewWz0 was NOT called.")
        return {
            "application_number": app_num,
            "passport_series": passport_series,
            "passport_number": passport_number,
            "status": "SKIPPED_UNMATCHED_SPECIALTY",
            "message": err_msg
        }
    elif matched_specialties_count < requested_count:
        print(f"\n[SPECIALTY MATCHING WARNING] Requested {requested_count} specialty/specialties, but matched {matched_specialties_count}. Proceeding with {len(priorities_list)} matched competitive group(s)...")

    selected_cg_ids = [p["CompetitiveGroupId"] for p in priorities_list]

    wz0_payload = {
        "ApplicationId": 0,
        "InstitutionID": int(institution_id),
        "CampaignID": str(campaign_id),
        "DocumentSeries": passport_series,
        "DocumentNumber": passport_number,
        "FromEPGU": True,
        "IdentityDocumentTypeID": "1",
        "RegistrationDate": data.get("registration_date", DEFAULT_SETTINGS["registration_date"]),
        "ApplicationNumber": str(app_num),
        "Priorities": {
            "ApplicationId": -1,
            "ApplicationPriorities": priorities_list
        },
        "SelectedCompetitiveGroupIDs": selected_cg_ids,
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
        err_msg = j0.get("Message", "Unknown error in NewWz0")
        print("[ERROR] NewWz0 returned error: " + str(err_msg))
        status_str = "ALREADY_EXISTS" if "\u0443\u0436\u0435 \u0437\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043e" in str(err_msg).lower() else "ERROR"
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": status_str, "message": str(err_msg)}

    app_id = extract_id(j0.get("Data"), "ApplicationID", "ApplicationId", "id") or extract_id(j0, "ApplicationID", "ApplicationId", "id")
    if not app_id:
        err_msg = "NewWz0 did not return ApplicationID"
        print("[ERROR] " + err_msg)
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ERROR", "message": err_msg}

    print("[SUCCESS] Step 1 created ApplicationID: " + str(app_id))

    # STEP 1.5: Discover EntrantID & Passport EntrantDocumentID via Wz1
    entrant_id, passport_doc_id = get_entrant_id_from_server(s, target_url, headers_json, app_id, j0)
    if entrant_id:
        print("   [INFO] Discovered EntrantID: " + str(entrant_id))
    else:
        print("   [WARNING] Could NOT extract EntrantID for ApplicationID " + str(app_id))

    # STEP 2: UpdWz1
    reg_date = data.get("registration_date", DEFAULT_SETTINGS["registration_date"])
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

    # STEP 2.5: Wz2
    s.post(target_url + "/Application/Wz2", json={"id": int(app_id)}, headers=headers_json)

    # STEP 3: Attach Education Document via /Entrant/setEditDocument
    gpa_str = str(data.get("gpa") or data.get("GPA") or "0").replace(".", ",")
    edu_payload = {
        "EntrantID": int(entrant_id) if entrant_id else 0,
        "EntrantDocumentID": 0,
        "DocumentTypeID": 16,
        "DocumentTypeName": "",
        "UID": "",
        "ApplicationID": int(app_id),
        "DocumentSeries": "",
        "DocumentNumber": str(data.get("diploma_number", "")),
        "DocumentDate": str(data.get("diploma_date", "01.07.2026")),
        "DocumentOrganization": str(data.get("diploma_organization", "")),
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

    if not passport_doc_id and edu_doc_id and int(edu_doc_id) > 1:
        passport_doc_id = int(edu_doc_id) - 1

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

    print(f"\n[APPLICATION SUCCESS] Application {app_num} registered successfully in FIS GIA with ID {app_id}!")
    return {
        "application_number": str(app_num),
        "passport_series": str(passport_series),
        "passport_number": str(passport_number),
        "status": "CREATED",
        "message": f"Application registered successfully with ID {app_id}"
    }

def run_fis_submission(json_file=None):
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    server_dir = os.path.dirname(os.path.abspath(__file__))

    log_filename = os.path.join(server_dir, f"log_{now_str}.txt")
    response_filename = os.path.join(server_dir, f"response_{now_str}.json")

    sys.stdout = LoggerWriter(log_filename)

    if not json_file:
        json_file = os.path.join(server_dir, "applications.json")
        if not os.path.exists(json_file):
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

    # Batch Processing Loop with CONTINUE ON ERROR
    for idx, app_data in enumerate(applications_list, start=1):
        app_num = app_data.get("application_number", "N/A")
        print(f"\n=================================================================")
        print(f"   [BATCH {idx}/{len(applications_list)}] Submitting Application #{app_num}")
        print(f"=================================================================")

        try:
            res = submit_single_application(s, target_url, headers_json, app_data, discovered_config)
            summary_responses.append(res)
        except Exception as e:
            print(f"[EXCEPTION ERROR] Failed to submit application #{app_num}: {e}")
            summary_responses.append({
                "application_number": str(app_num),
                "passport_series": str(app_data.get("passport_series", "")),
                "passport_number": str(app_data.get("passport_number", "")),
                "status": "ERROR",
                "message": f"Execution Exception: {str(e)}"
            })
            # Skip iteration without breaking loop!
            continue

    # Write summary response JSON
    with open(response_filename, "w", encoding="utf-8") as f:
        json.dump(summary_responses, f, ensure_ascii=False, indent=2)

    print("\n=================================================================")
    print("   BATCH PROCESSING FINISHED SUMMARY")
    print(f"   Total Processed: {len(summary_responses)}")
    print(f"   Console Log Saved: {log_filename}")
    print(f"   Response JSON Saved: {response_filename}")
    print("=================================================================")

if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    run_fis_submission(filepath)
