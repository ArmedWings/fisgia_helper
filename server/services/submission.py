# -*- coding: utf-8 -*-
"""
Single application submission pipeline for FIS GIA.
Executes the full multi-step wizard:
- Step 1: NewWz0 (Draft creation & duplicate check)
- Step 1.5: Entrant ID resolution
- Step 2: UpdWz1 (Personal & Identity details)
- Step 3: setEditDocument (Education certificate & Original confirmation)
- Step 4: SaveWz5 (Priorities & Status finalization)
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from core.config import DEFAULT_SETTINGS
from core.helpers import format_gpa, extract_id, get_region_id, get_town_type_id
from services.specialties import resolve_competitive_group_ids_with_names
from services.fis_client import (
    get_entrant_id_from_server,
    get_passport_doc_id,
    check_existing_application,
    delete_draft_application
)


def submit_single_application(s, target_url, headers_json, data, discovered_config):
    """
    Submits a single entrant's application to FIS GIA through all wizard steps.
    """
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
        is_num_in_use = ("используется" in err_msg.lower() or "номер" in err_msg.lower() or "already" in err_msg.lower())
        status_code = "ERROR_APP_NUMBER_EXISTS" if is_num_in_use else "ERROR"
        return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": status_code, "message": err_msg}

    data0 = j0.get("Data") if isinstance(j0.get("Data"), dict) else j0
    app_id = extract_id(data0, "ApplicationID", "ApplicationId", "id") or extract_id(j0, "ApplicationID", "ApplicationId", "id")
    entrant_is_new = data0.get("EntrantIsNew") if isinstance(data0, dict) else j0.get("EntrantIsNew")

    entrant_id = None

    if not app_id or app_id == 0 or entrant_is_new is False:
        if passport_series and passport_number:
            print(f"[CHECK EXISTING APP] EntrantIsNew = False for passport {passport_series} {passport_number}. Querying LoadApplicationNewRecords...")
            has_existing_app, existing_app_info, found_eid = check_existing_application(
                s, target_url, headers_json, passport_series, passport_number, campaign_id, app_id
            )
            if found_eid:
                entrant_id = found_eid

            if has_existing_app:
                existing_num = existing_app_info.get("ApplicationNumber") if existing_app_info else "N/A"
                existing_id = existing_app_info.get("ApplicationId") if existing_app_info else "N/A"
                msg = f"Entrant already has an application in FIS GIA (Application #{existing_num}, ID {existing_id})"
                print(f"[ALREADY EXISTS] {msg}. Deleting draft application {app_id}...")
                delete_draft_application(s, target_url, headers_json, app_id)
                return {"application_number": app_num, "passport_series": passport_series, "passport_number": passport_number, "status": "ALREADY_EXISTS", "message": msg}

        print(f"[NEW APPLICATION FOR EXISTING ENTRANT] EntrantIsNew = False, but NO OTHER application found for passport {passport_series} {passport_number}. Continuing submission with draft ApplicationID {app_id}...")

    print("[SUCCESS] Step 1 created ApplicationID: " + str(app_id))

    # STEP 1.5: Discover EntrantID
    discovered_eid, passport_doc_id = get_entrant_id_from_server(s, target_url, headers_json, app_id, j0)
    if discovered_eid:
        entrant_id = discovered_eid

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
        "GenderID": "1" if data.get("gender") == "Мужской" else "2",
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
        "ReleasePlace": "Россия",
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
