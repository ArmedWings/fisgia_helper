# -*- coding: utf-8 -*-
"""
Client for interacting with BARS.Education (M3 Platform API) using session cookies.
"""

import os
import json
import logging
import requests

from config import load_client_env, DEFAULT_BARS_URL
from parsers import format_date_filter, parse_extjs_js

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BarsClient:
    """
    Client for interacting with BARS.Education (M3 Platform API)
    using session cookies.
    """

    def __init__(self, base_url=None, session_id=None, csrf_token=None):
        load_client_env()

        self.base_url = (base_url or os.getenv('BARS_BASE_URL', DEFAULT_BARS_URL)).rstrip('/')
        self.session_id = session_id or os.getenv('SSUZ_SESSIONID', '')
        self.csrf_token = csrf_token or os.getenv('CSRFTOKEN', '')

        if not self.session_id or not self.csrf_token:
            logger.warning("[BARS] Warning: SSUZ_SESSIONID or CSRFTOKEN not found in .env / config.env!")

        self.session = requests.Session()
        domain = self.base_url.replace('https://', '').replace('http://', '').split('/')[0]

        self.session.cookies.set('userNotifiedAboutCookieUsage', 't', domain=domain)
        self.session.cookies.set('csrf_token_header_name', 'X-CSRFToken', domain=domain)
        self.session.cookies.set('ssuz_sessionid', self.session_id, domain=domain)
        self.session.cookies.set('csrftoken', self.csrf_token, domain=domain)

        cookie_header_str = f"userNotifiedAboutCookieUsage=t; csrf_token_header_name=X-CSRFToken; ssuz_sessionid={self.session_id}; csrftoken={self.csrf_token}"

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': self.csrf_token,
            'Origin': self.base_url,
            'Referer': f"{self.base_url}/desk/",
            'Cookie': cookie_header_str
        })

    def execute_action(self, pack_path: str, action_name: str = "objectrowsaction", payload: dict = None, silent: bool = False) -> dict:
        """
        Executes an action on the BARS M3 endpoint via HTTP POST.
        """
        url = f"{self.base_url}/actions/{pack_path}/{action_name}"
        payload = payload or {}

        try:
            response = self.session.post(url, data=payload, timeout=30)
            if response.status_code != 200:
                if not silent:
                    logger.error(f"[BARS ERROR] HTTP {response.status_code} from {url}")
                return {"error": f"HTTP {response.status_code}", "body": response.text[:300]}

            raw_text = response.text
            try:
                data = response.json()
                if isinstance(data, dict):
                    if data.get("success") is False and "не авторизован" in str(data.get("message", "")).lower():
                        logger.error("[BARS ERROR] Session expired! Please update SSUZ_SESSIONID and CSRFTOKEN in client config")
                    data["_raw_text"] = raw_text
                    return data
                return {"data": data, "_raw_text": raw_text}
            except json.JSONDecodeError:
                return {"_raw_text": raw_text, "raw_text": raw_text, "is_json": False}

        except Exception as e:
            logger.error(f"[BARS ERROR] Exception during POST to {url}: {e}")
            return {"error": str(e)}

    def get_periods(self) -> list:
        """
        Queries BARS for admission periods:
        POST /actions/period/objectrowsaction
        """
        payload = {
            'start': 0,
            'limit': 50,
            'period_id': '',
            'm3_window_id': 'cmp_266a9153',
            'filter': ''
        }
        res = self.execute_action("period", "objectrowsaction", payload)
        if isinstance(res, dict) and "rows" in res:
            return res.get("rows", [])
        elif isinstance(res, list):
            return res
        return []

    def get_declarations_list(
        self,
        period_id: int,
        start: int = 0,
        limit: int = 25,
        sort: str = "date",
        dir_order: str = "DESC",
        filter_text: str = None,
        filter_1: str = None,
        filter_2: str = None
    ) -> dict:
        """
        Queries BARS declarations list filtered by period_id, limit, start, search filters, and sorting:
        POST /actions/declaration/objectrowsaction
        """
        payload = {
            'period_id': period_id,
            'limit': limit,
            'start': start,
            'm3_window_id': 'cmp_266a9153',
            'grid_id': 'cmp_17688a62'
        }
        if sort:
            payload['sort'] = sort
        if dir_order:
            payload['dir'] = dir_order
        if filter_text:
            payload['filter'] = filter_text
        if filter_1:
            f1 = format_date_filter(filter_1)
            if f1:
                payload['filter_1'] = f1
        if filter_2:
            f2 = format_date_filter(filter_2)
            if f2:
                payload['filter_2'] = f2

        return self.execute_action("declaration", "objectrowsaction", payload)

    def get_declaration_plans(self, declaration_id: int, period_id: int = None, unit_id: int = None, finished_forms: int = 1, m3_window_id: str = "", grid_id: str = "") -> dict:
        """
        Queries declaration educational plans from BARS.
        """
        payload = {
            'limit': 50,
            'start': 0,
            'declaration_id': declaration_id,
            'period_id': period_id or 41,
            'unit_id': unit_id or 26,
            'finished_forms': finished_forms or 1
        }
        if m3_window_id:
            payload['m3_window_id'] = m3_window_id
        if grid_id:
            payload['grid_id'] = grid_id

        pack = "ssuz.declaration.actions.PlansForDeclarationPack"
        action = "_plansfordeclarationrowsaction"
        return self.execute_action(pack, action, payload, silent=True)

    def get_declaration_edit_window(self, declaration_id: int, period_id: int = None) -> dict:
        """
        Queries declaration edit window containing form fields and ExtJS definitions.
        """
        payload = {
            'object_id': declaration_id,
            'id': declaration_id,
            'declaration_id': declaration_id
        }
        return self.execute_action("declaration", "declarationeditwindowaction", payload)

    def get_enrollee_details(self, enrollee_id: int) -> dict:
        """
        Queries enrollee details using multiple fallback packs.
        """
        payload = {
            'object_id': enrollee_id,
            'id': enrollee_id,
            'enrollee_id': enrollee_id
        }
        candidates = [
            ("ssuz.enrollee.ui.actions.EnrolleePack", "objecteditwindowaction"),
            ("ssuz.enrollee.ui.actions.EnrolleePack", "editwindowaction"),
            ("ssuz.enrollee.ui.actions.EnrolleePack", "objectrowsaction"),
            ("enrollee", "objecteditwindowaction"),
            ("enrollee", "editwindowaction"),
            ("enrollee", "objectrowsaction")
        ]
        for pack, action in candidates:
            res = self.execute_action(pack, action, payload, silent=True)
            if isinstance(res, dict) and "error" not in res:
                return res
        return {}

    def parse_extjs_js(self, js_content: str) -> dict:
        """
        Helper method calling standalone ExtJS parser.
        """
        return parse_extjs_js(js_content)
