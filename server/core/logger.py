# -*- coding: utf-8 -*-
"""
Logging utilities for FIS GIA server integration.
Provides TeeLogger to pipe stdout simultaneously to console and a timestamped log file.
"""

import sys


class TeeLogger:
    """
    Tee logger to write stdout simultaneously to the console and a file.
    """

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
        try:
            self.log_file.close()
        except Exception:
            pass
