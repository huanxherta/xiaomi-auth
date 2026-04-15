import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import Optional


class BrowserConfig(BaseModel):
    engine: str = "chromium"
    headless: bool = False
    slow_mo: int = 100
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: str = ""
    locale: str = "zh-TW"
    timezone: str = "Asia/Taipei"


class AuthConfig(BaseModel):
    base_url: str
    login_url: str
    xiaomi_account_base: str
    global_account_base: str
    sid: str
    service_id: str


class CaptchaConfig(BaseModel):
    wait_timeout: int = 300


class StorageConfig(BaseModel):
    cookies_dir: str = "cookies"
    logs_dir: str = "logs"


class Config(BaseModel):
    browser: BrowserConfig
    auth: AuthConfig
    captcha: CaptchaConfig
    storage: StorageConfig

    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "Config":
        path = Path(config_path)
        if not path.is_absolute():
            path = Path(__file__).parent.parent.parent / config_path

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        browser_data = data.get("browser", {})
        auth_data = data.get("auth", {})
        captcha_data = data.get("captcha", {})
        storage_data = data.get("storage", {})

        return cls(
            browser=BrowserConfig(
                engine=browser_data.get("engine", "chromium"),
                headless=browser_data.get("headless", False),
                slow_mo=browser_data.get("slow_mo", 100),
                viewport_width=browser_data.get("viewport", {}).get("width", 1280),
                viewport_height=browser_data.get("viewport", {}).get("height", 800),
                user_agent=browser_data.get("user_agent", ""),
                locale=browser_data.get("locale", "zh-TW"),
                timezone=browser_data.get("timezone", "Asia/Taipei"),
            ),
            auth=AuthConfig(**auth_data),
            captcha=CaptchaConfig(**captcha_data),
            storage=StorageConfig(**storage_data),
        )
