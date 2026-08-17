# -*- coding: utf-8 -*-
"""
Core utilities and configuration for FIS GIA server integration.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from .config import load_server_env, FIS_BASE_URL, DEFAULT_SETTINGS, REGION_MAP, ACCESS_TOKEN, REFRESH_TOKEN
from .logger import TeeLogger
from .helpers import format_gpa, extract_id, get_region_id, get_town_type_id, extract_numeric_suffix, load_json_file
