from playwright.async_api import Page
from typing import Optional
from urllib.parse import urlparse, parse_qs
from src.utils.config import Config
from src.utils.logger import get_logger
from src.browser.captcha_handler import CaptchaHandler

logger = get_logger()


class LoginHandler:
    def __init__(self, page: Page, config: Config, captcha_handler: CaptchaHandler):
        self.page = page
        self.config = config
        self.captcha_handler = captcha_handler

    async def navigate_to_login(self) -> Optional[str]:
        logger.info("正在获取登录入口URL...")

        await self.page.goto(self.config.auth.login_url, wait_until="networkidle")

        await self.page.wait_for_timeout(2000)

        current_url = self.page.url
        logger.info(f"当前URL: {current_url}")

        if (
            "account.xiaomi.com" in current_url
            or "global.account.xiaomi.com" in current_url
        ):
            logger.success("成功到达小米账号登录页面")
            return current_url

        await self.page.wait_for_load_state("networkidle")
        return self.page.url

    async def check_for_captcha(self) -> bool:
        page_content = await self.page.content()

        captcha_indicators = [
            "captcha",
            "verify",
            "geetest",
            "slider",
            "miverify",
            "img_captcha",
        ]

        for indicator in captcha_indicators:
            if indicator in page_content.lower():
                logger.info(f"检测到验证码标识: {indicator}")
                return True

        return await self.captcha_handler.is_on_captcha_page()

    async def handle_captcha_if_needed(self):
        if await self.check_for_captcha():
            await self.captcha_handler.wait_for_manual_captcha("登录验证码")

    async def perform_login(
        self, account: str, password: str, wait_for_sts: bool = True
    ) -> bool:
        logger.info(f"开始登录流程, 账号: {account}")

        try:
            await self._handle_login_form(account, password)

            await self.handle_captcha_if_needed()

            if wait_for_sts:
                return await self._wait_for_sts_callback()

            return True

        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            return False

    async def _handle_login_form(self, account: str, password: str):
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_timeout(1000)

        username_selectors = [
            'input[name="user"]',
            'input[placeholder*="账号"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="手机"]',
            'input[id*="account"]',
            'input[type="text"]:visible',
            "#username",
        ]

        username_input = None
        for selector in username_selectors:
            try:
                username_input = await self.page.wait_for_selector(
                    selector, timeout=3000
                )
                if username_input:
                    logger.debug(f"找到用户名输入框: {selector}")
                    break
            except Exception:
                continue

        if not username_input:
            logger.error("未找到用户名输入框")
            raise Exception("找不到登录表单的用户名输入框")

        await username_input.fill(account)
        logger.debug("已填入账号")

        password_selectors = [
            'input[name="pwd"]',
            'input[name="password"]',
            'input[type="password"]:visible',
            'input[placeholder*="密码"]',
            "#password",
        ]

        password_input = None
        for selector in password_selectors:
            try:
                password_input = await self.page.wait_for_selector(
                    selector, timeout=3000
                )
                if password_input:
                    logger.debug(f"找到密码输入框: {selector}")
                    break
            except Exception:
                continue

        if not password_input:
            logger.error("未找到密码输入框")
            raise Exception("找不到登录表单的密码输入框")

        await password_input.fill(password)
        logger.debug("已填入密码")

        await self.page.wait_for_timeout(500)

        login_button_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("登入")',
            ".login-btn",
            "#login-button",
        ]

        for selector in login_button_selectors:
            try:
                login_btn = await self.page.wait_for_selector(selector, timeout=2000)
                if login_btn:
                    logger.debug(f"找到登录按钮: {selector}")
                    await login_btn.click()
                    logger.info("已点击登录按钮")
                    break
            except Exception:
                continue

    async def _wait_for_sts_callback(self, timeout: int = 60000) -> bool:
        logger.info("等待登录完成, 跳转到目标站点...")

        try:
            await self.page.wait_for_url(
                "**/aistudio.xiaomimimo.com/**", timeout=timeout
            )
            logger.success(f"登录成功! 当前URL: {self.page.url}")
            return True
        except Exception:
            current_url = self.page.url
            if "aistudio.xiaomimimo.com" in current_url:
                logger.success(f"登录成功! 当前URL: {current_url}")
                return True

            logger.warning(f"登录可能需要验证码或出现错误, 当前URL: {current_url}")
            await self.captcha_handler.wait_for_manual_captcha("完成登录流程")

            return "aistudio.xiaomimimo.com" in self.page.url
