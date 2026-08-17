# -*- coding: utf-8 -*-
"""
Configuration management and environment parser for FIS GIA server integration.
Supports multi-environment setups (dev.env, prod.env, .env) and CLI overrides.
"""

import os
import sys

# Windows 7 Console UTF-8 Fix
if sys.platform == 'win32':
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass


def load_server_env(server_dir=None, argv=None):
    """
    Determines active environment (dev/prod) and loads variables from the corresponding .env file.
    Supports CLI flags: --prod, --dev, --env=prod, --env=dev.
    """
    if server_dir is None:
        # server/core -> parent is server/
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if argv is None:
        argv = sys.argv

    # Determine env mode (--prod, --dev, --env=prod, --env=dev, or os.environ APP_ENV/ENV_MODE, default 'dev')
    env_mode = os.getenv("APP_ENV", os.getenv("ENV_MODE", "dev")).lower().strip()
    for arg in argv:
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


# Auto-load on import
load_server_env()

# Central Constants & Settings
FIS_BASE_URL = os.getenv("FIS_BASE_URL", "http://10.0.3.1:8383").rstrip('/')
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")

DEFAULT_SETTINGS = {
    "default_app_number": "294-19",
    "registration_date": "05.08.2019",
    "status_id": 1,
    "is_epgu": True
}

REGION_MAP = {
    "владимир": "33",
    "москв": "77",
    "московск": "50",
    "иванов": "37",
    "нижегород": "52",
    "нижний новгород": "52",
    "рязан": "62",
    "ярославл": "76",
    "твер": "69",
    "тул": "71",
    "калуг": "40",
    "петербург": "78"
}
