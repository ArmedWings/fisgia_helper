# -*- coding: utf-8 -*-
"""
FIS GIA Integration Script
Processes applications list JSON and submits applications to FIS GIA via REST API.

This file serves as the main entry point and facade module, exposing all key functions
for backward compatibility while delegating logic to modular packages:
  - core/ (config, logger, helpers)
  - services/ (specialties, fis_client, submission, batch_runner)
"""

import os
import sys

# Ensure server directory is in sys.path
server_dir = os.path.dirname(os.path.abspath(__file__))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# Core imports
from core.config import (
    load_server_env,
    FIS_BASE_URL,
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    DEFAULT_SETTINGS,
    REGION_MAP
)
from core.logger import TeeLogger
from core.helpers import (
    format_gpa,
    extract_id,
    get_region_id,
    get_town_type_id,
    extract_numeric_suffix,
    load_json_file
)

# Services imports
from services.specialties import (
    load_specialty_prefix_map,
    resolve_competitive_group_ids_with_names
)
from services.fis_client import (
    refresh_session_auth,
    auto_discover_campaign_params,
    get_entrant_id_from_server,
    get_passport_doc_id,
    check_existing_application,
    delete_draft_application
)
from services.submission import submit_single_application
from services.batch_runner import run_fis_submission

# Expose SPECIALTY_PREFIX_MAP for direct backward compatibility
SPECIALTY_PREFIX_MAP = load_specialty_prefix_map()


if __name__ == "__main__":
    filepath = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and arg.lower() not in ["dev", "prod"]:
            if arg.endswith(".json") or os.path.exists(arg):
                filepath = arg
                break
    run_fis_submission(filepath)
