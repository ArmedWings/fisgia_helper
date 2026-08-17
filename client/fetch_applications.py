# -*- coding: utf-8 -*-

# Main CLI entry point for BARS.Education declarations extraction.
# Fetches declarations from BARS and writes formatted applications to applications.json.

import os
import sys

# Ensure client directory is in sys.path
client_dir = os.path.dirname(os.path.abspath(__file__))
if client_dir not in sys.path:
    sys.path.insert(0, client_dir)

from config import load_client_env
from bars_client import BarsClient
from parsers import parse_selected_specialties, format_date_filter
from extractor import fetch_and_export_applications, generate_random_app_number

if __name__ == "__main__":
    fetch_and_export_applications()
