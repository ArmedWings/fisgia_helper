# -*- coding: utf-8 -*-
"""
Configuration management and environment loader for BARS.Education client.
"""

import os
import sys

# Windows Console UTF-8 Fix
if sys.platform == 'win32':
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass


def load_client_env(base_dir=None):
    """
    Loads environment variables from config.env or .env in the client directory.
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    candidate_files = ['config.env', '.env']
    loaded_file = None

    for filename in candidate_files:
        env_path = os.path.join(base_dir, filename)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            if k and k not in os.environ:
                                os.environ[k] = v
                loaded_file = env_path
                break
            except Exception:
                pass

    return loaded_file


# Auto-load on import
load_client_env()

# Default constants
DEFAULT_BARS_URL = "https://xn--n1abf.xn--33-6kcadhwnl3cfdx.xn--p1ai"
