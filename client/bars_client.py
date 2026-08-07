# -*- coding: utf-8 -*-
import os
import re
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BarsClient:
    """
    Client for interacting with BARS.Education (M3 Platform API)
    using session cookies.
    """

    def __init__(self, base_url=None, session_id=None, csrf_token=None):
        client_dir = os.path.dirname(__file__)
        for filename in ['config.env', '.env']:
            env_path = os.path.join(client_dir, filename)
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
                    break
                except Exception:
                    pass

        self.base_url = (base_url or os.getenv('BARS_BASE_URL', 'https://xn--n1abf.xn--33-6kcadhwnl3cfdx.xn--p1ai')).rstrip('/')
        self.session_id = session_id or os.getenv('SSUZ_SESSIONID', '')
        self.csrf_token = csrf_token or os.getenv('CSRFTOKEN', '')

        if not self.session_id or not self.csrf_token:
            logger.warning("[BARS] Warning: SSUZ_SESSIONID or CSRFTOKEN not found in .env!")

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
                    if data.get("success") is False and "\u043d\u0435 \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u043e\u0432\u0430\u043d\u044b" in data.get("message", ""):
                        logger.error("[BARS ERROR] Session expired! Please update SSUZ_SESSIONID and CSRFTOKEN in client/.env")
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

    def get_declarations_list(self, period_id: int, start: int = 0, limit: int = 25) -> dict:
        """
        Queries BARS declarations list filtered by period_id, limit, start:
        POST /actions/declaration/objectrowsaction
        """
        payload = {
            'period_id': period_id,
            'limit': limit,
            'start': start,
            'm3_window_id': 'cmp_266a9153',
            'grid_id': 'cmp_17688a62'
        }
        return self.execute_action("declaration", "objectrowsaction", payload)

    def get_declaration_plans(self, declaration_id: int, period_id: int = None, unit_id: int = None, finished_forms: int = 1, m3_window_id: str = "", grid_id: str = "") -> dict:
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
        payload = {
            'object_id': declaration_id,
            'id': declaration_id,
            'declaration_id': declaration_id
        }
        return self.execute_action("declaration", "declarationeditwindowaction", payload)

    def get_enrollee_details(self, enrollee_id: int) -> dict:
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
        extracted_data = {}
        pattern = re.compile(
            r"name\s*:\s*['\"](?P<name>[^'\"]+)['\"]"
            r"(?:(?!new Ext\.).)*?"
            r"(?:value\s*:\s*(?P<val_str>'[^']*'|\"[^\"]*\"|\d+(?:\.\d+)?|true|false)|defaultText\s*:\s*['\"](?P<def_text>[^'\"]+)['\"])",
            re.DOTALL
        )
        for match in pattern.finditer(js_content):
            name = match.group('name')
            val_str = match.group('val_str')
            def_text = match.group('def_text')
            
            if val_str:
                if (val_str.startswith("'") and val_str.endswith("'")) or (val_str.startswith('"') and val_str.endswith('"')):
                    val = val_str[1:-1]
                else:
                    val = val_str
            elif def_text:
                val = def_text
            else:
                val = ""
                
            if name not in extracted_data or val != "":
                extracted_data[name] = val
                
        return extracted_data
