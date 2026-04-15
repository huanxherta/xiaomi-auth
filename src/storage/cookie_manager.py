import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.utils.logger import get_logger

logger = get_logger()


def _normalize_cookie_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


class CookieManager:
    def __init__(self, cookies_dir: str = "cookies"):
        self.cookies_dir = Path(cookies_dir)
        if not self.cookies_dir.is_absolute():
            self.cookies_dir = Path(__file__).parent.parent.parent / cookies_dir
        self.cookies_dir.mkdir(parents=True, exist_ok=True)

    def _get_cookie_path(self, account: str) -> Path:
        safe_account = account.replace("@", "_at_").replace(".", "_")
        return self.cookies_dir / f"{safe_account}.json"

    def save_cookies(
        self,
        cookies: List[Dict[str, Any]],
        account: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        cookie_path = self._get_cookie_path(account)

        data = {
            "account": account,
            "cookies": cookies,
            "saved_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Cookies saved to: {cookie_path}")
        return cookie_path

    def save_auth_data(
        self,
        account: str,
        service_token: str = None,
        user_id: str = None,
        xiaomichatbot_ph: str = None,
        cookies: List[Dict[str, Any]] = None,
        local_storage: Dict[str, Any] = None,
    ) -> Path:
        cookie_path = self._get_cookie_path(account)

        service_token = _normalize_cookie_value(service_token)
        user_id = _normalize_cookie_value(user_id)
        xiaomichatbot_ph = _normalize_cookie_value(xiaomichatbot_ph)

        data = {
            "account": account,
            "saved_at": datetime.now().isoformat(),
            "auth": {
                "serviceToken": service_token,
                "userId": user_id,
                "xiaomichatbot_ph": xiaomichatbot_ph,
            },
            "cookies": cookies or [],
            "localStorage": local_storage or {},
        }

        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.success(f"Auth data saved to: {cookie_path}")
        return cookie_path

    def load_cookies(self, account: str) -> Optional[List[Dict[str, Any]]]:
        cookie_path = self._get_cookie_path(account)

        if not cookie_path.exists():
            logger.warning(f"No cookie file found: {cookie_path}")
            return None

        with open(cookie_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info(f"Cookies loaded from: {cookie_path}")
        return data.get("cookies", [])

    def load_auth_data(self, account: str) -> Optional[Dict[str, Any]]:
        cookie_path = self._get_cookie_path(account)

        if not cookie_path.exists():
            return None

        with open(cookie_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete_cookies(self, account: str) -> bool:
        cookie_path = self._get_cookie_path(account)

        if cookie_path.exists():
            cookie_path.unlink()
            logger.info(f"Cookies deleted: {cookie_path}")
            return True

        return False

    def list_saved_accounts(self) -> List[str]:
        accounts = []
        for cookie_file in self.cookies_dir.glob("*.json"):
            with open(cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "account" in data:
                    accounts.append(data["account"])
        return accounts
