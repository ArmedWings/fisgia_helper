# -*- coding: utf-8 -*-
"""
HTTP Client and API helpers for FIS GIA (Fis GIA REST and WZ endpoints).
Handles token refresh, dynamic campaign discovery, entrant/document identification,
and draft management.
"""

import os
import sys
import re
import json
from datetime import datetime

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from core.helpers import extract_id
from core.config import ACCESS_TOKEN, REFRESH_TOKEN


def refresh_session_auth(session, target_url, access_token=None, refresh_token=None):
    """
    Warms up session and refreshes access token against FIS GIA account endpoints.
    """
    print("[AUTH] Warming up session and refreshing access token...")
    auth_urls = [
        target_url + "/Account/Refresh",
        target_url + "/Account/RefreshToken",
        target_url + "/api/account/refresh"
    ]
    cur_access = access_token or os.getenv("ACCESS_TOKEN") or ACCESS_TOKEN
    cur_refresh = refresh_token or os.getenv("REFRESH_TOKEN") or REFRESH_TOKEN

    payload = {
        "accessToken": cur_access,
        "refreshToken": cur_refresh
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8"
    }

    result_token = cur_access
    for url in auth_urls:
        try:
            r = session.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                j = r.json()
                token = j.get("access_token") or j.get("fisAccess") or j.get("token")
                if token:
                    result_token = token
                    print("[AUTH SUCCESS] Acquired fisAccess token via " + str(url))
                    break
        except Exception:
            pass

    return result_token


def auto_discover_campaign_params(session, target_url, headers_json):
    """
    Discovers active CampaignID, InstitutionID, and all Competitive Groups
    dynamically from the FIS GIA server.
    """
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

                        prefix = re.sub(r'[\d\-]+$', '', cg_name.lower()).rstrip("з").strip()
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


def get_entrant_id_from_server(s, target_url, headers_json, app_id, j0):
    """
    Extracts EntrantID and IdentityDocumentID from Wz0 response,
    or falls back to querying /Application/Wz1.
    """
    d0 = j0.get("Data") if isinstance(j0, dict) and isinstance(j0.get("Data"), dict) else (j0 if isinstance(j0, dict) else {})
    eid = extract_id(d0, "EntrantID", "EntrantId")
    pid = extract_id(d0, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID")
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
                match = (
                    re.search(r'<input[^>]*id=["\']EntrantID["\'][^>]*value=["\'](\d+)["\']', text_wz1, re.IGNORECASE) or
                    re.search(r'<input[^>]*name=["\']EntrantID["\'][^>]*value=["\'](\d+)["\']', text_wz1, re.IGNORECASE) or
                    re.search(r'<input[^>]*value=["\'](\d+)["\'][^>]*id=["\']EntrantID["\']', text_wz1, re.IGNORECASE) or
                    re.search(r'<input[^>]*value=["\'](\d+)["\'][^>]*name=["\']EntrantID["\']', text_wz1, re.IGNORECASE) or
                    re.search(r'EntrantID["\s:=]+(\d+)', text_wz1, re.IGNORECASE)
                )
                if match:
                    eid = int(match.group(1))
    except Exception as err:
        print(f"   [WARNING] Failed to query /Application/Wz1: {err}")

    return eid, pid


def get_passport_doc_id(s, target_url, headers_json, app_id, edu_doc_id, entrant_id=None, j0=None, j1=None):
    """
    Identifies the EntrantDocumentID corresponding to the passport.
    First checks /Entrant/getEntrantDocuments, then checks j1 / j0 response objects.
    """
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
                        if dt_id == 1 or "паспорт" in dt_name:
                            p_id = doc.get("EntrantDocumentID")
                            if p_id and int(p_id) > 0:
                                return int(p_id)
        except Exception as e:
            print(f"   [WARNING] Failed to query getEntrantDocuments: {e}")

    # 2. Check j1 / j0 JSON responses
    for source in [j1, j0]:
        if isinstance(source, dict):
            pid = (
                extract_id(source.get("Data"), "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID") or
                extract_id(source, "EntrantDocumentID", "EntrantDocumentId", "IdentityDocumentID", "DocumentID")
            )
            if pid and pid > 10000000 and pid != int(edu_doc_id):
                return pid

    return None


def check_existing_application(s, target_url, headers_json, passport_series, passport_number, campaign_id, current_app_id):
    """
    Checks if applicant already has a registered application in FIS GIA
    via /InstitutionApplication/LoadApplicationNewRecords.
    Returns: (has_existing_app: bool, existing_app_info: dict|None, entrant_id: int|None)
    """
    has_existing_app = False
    existing_app_info = None
    entrant_id = None

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
                    if found_app_id and int(found_app_id) > 0 and (not current_app_id or int(found_app_id) != int(current_app_id)):
                        has_existing_app = True
                        existing_app_info = rec
                        break
    except Exception as search_err:
        print(f"   [WARNING] Failed to query LoadApplicationNewRecords: {search_err}")

    return has_existing_app, existing_app_info, entrant_id


def delete_draft_application(s, target_url, headers_json, app_id):
    """
    Deletes an unneeded draft application from FIS GIA via /InstitutionApplication/DeleteApplications.
    """
    if not app_id or int(app_id) <= 0:
        return
    try:
        del_res = s.post(target_url + "/InstitutionApplication/DeleteApplications", json={"applicationId": [int(app_id)]}, headers=headers_json)
        print(f"   [DELETED DRAFT] Deleted draft ApplicationID {app_id} (HTTP {del_res.status_code}: {del_res.text[:150]})")
    except Exception as del_err:
        print(f"   [WARNING] Failed to delete draft ApplicationID {app_id}: {del_err}")
