# -*- coding: utf-8 -*-
"""
Business logic and integration services for FIS GIA submission.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from .specialties import load_specialty_prefix_map, resolve_competitive_group_ids_with_names
from .fis_client import (
    refresh_session_auth,
    auto_discover_campaign_params,
    get_entrant_id_from_server,
    get_passport_doc_id,
    check_existing_application,
    delete_draft_application
)
from .submission import submit_single_application
from .batch_runner import run_fis_submission
