from playwright.async_api import Page
from typing import Optional
import asyncio
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.temp_mail import TempMailClient
from src.browser.captcha_handler import CaptchaHandler

logger = get_logger()


class RegisterHandler:
    def __init__(
        self,
        page: Page,
        config: Config,
        captcha_handler: CaptchaHandler,
        mail_client: Optional[TempMailClient] = None,
    ):
        self.page = page
        self.config = config
        self.captcha_handler = captcha_handler
        self.mail_client = mail_client

    async def navigate_to_register(self) -> bool:
        logger.info("正在导航到注册页面...")

        register_url = f"{self.config.auth.global_account_base}/fe/service/register?sid={self.config.auth.sid}&_locale=zh_TW&_uRegion=US"
        logger.info(f"Navigate to: {register_url}")
        await self.page.goto(register_url, wait_until="networkidle", timeout=60000)

        return True

    async def perform_register(
        self, email: str, password: str, region: str = "TW", auto_verify: bool = True
    ) -> bool:
        logger.info(f"开始注册流程, 邮箱: {email}")

        try:
            await self._handle_register_form(email, password, region)

            await self.page.wait_for_timeout(2000)

            if await self._check_for_captcha():
                await self.captcha_handler.wait_for_manual_captcha("注册验证码")

            await self.page.wait_for_timeout(2000)

            if auto_verify and self.mail_client:
                await self._handle_email_verification_auto(email)

            await self.page.wait_for_timeout(2000)
            await self._handle_post_submit_states(email, auto_verify)

            return await self._wait_for_sts_callback()

        except Exception as e:
            logger.error(f"注册过程出错: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def _handle_post_submit_states(self, email: str, auto_verify: bool):
        for attempt in range(6):
            current_url = self.page.url
            logger.info(f"检查提交后状态，第 {attempt + 1} 次: {current_url}")

            if "aistudio.xiaomimimo.com" in current_url:
                return

            if "verifyEmail" in current_url or await self._check_verify_email_page():
                logger.info("命中 verifyEmail 页面，开始处理二次邮箱验证")
                if auto_verify and self.mail_client:
                    await self._handle_second_verification(email)
                    await self.page.wait_for_timeout(2500)
                    continue
                await self.captcha_handler.wait_for_manual_captcha("二次邮箱验证")
                return

            if "account.xiaomi.com/fe/service/account" in current_url:
                logger.info("已到账号完成页，立即跳转到 aistudio")
                await self.page.goto(
                    "https://aistudio.xiaomimimo.com/#/",
                    wait_until="networkidle",
                    timeout=60000,
                )
                await self.page.wait_for_timeout(5000)
                return

            await self.page.wait_for_timeout(1500)

    async def _check_verify_email_page(self) -> bool:
        try:
            if "verifyEmail" in self.page.url:
                return True

            page_content = await self.page.content()
            if "驗證您的安全信箱" in page_content or "验证您的安全信箱" in page_content:
                return True
            if "傳送信件" in page_content or "发送信件" in page_content:
                return True
        except Exception:
            pass
        return False

    async def _handle_second_verification(self, email: str):
        logger.info("处理二次邮箱验证...")

        clicked = False

        for text in ["傳送信件", "发送信件", "傳送", "发送"]:
            try:
                locator = self.page.get_by_text(text, exact=True)
                if await locator.count() > 0:
                    await locator.first.click(timeout=5000)
                    logger.info(f"已点击按钮: {text}")
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            for selector in [
                'button[type="submit"]',
                ".ant-btn",
                "button",
                '[role="button"]',
            ]:
                try:
                    buttons = await self.page.query_selector_all(selector)
                    for button in buttons:
                        text = (await button.inner_text()).strip()
                        if text in {"傳送信件", "发送信件", "傳送", "发送"}:
                            await button.click()
                            logger.info(f"已点击按钮文本: {text}")
                            clicked = True
                            break
                    if clicked:
                        break
                except Exception:
                    continue

        if not clicked:
            logger.warning("未自动找到傳送信件按钮，切换人工处理")
            await self.captcha_handler.wait_for_manual_captcha("点击傳送信件")

        await self.page.wait_for_timeout(3000)

        code = await self.mail_client.wait_for_verification_code(
            sender_pattern="xiaomi",
            timeout=300,
            poll_interval=3,
        )

        if not code:
            logger.warning("未获取到二次验证码, 等待人工输入...")
            await self.captcha_handler.wait_for_manual_captcha("二次验证码")
            return

        code_input_selectors = [
            'input[name*="code"]',
            'input[name*="verify"]',
            'input[id*="code"]',
            'input[placeholder*="验证"]',
            'input[type="text"]',
        ]

        for selector in code_input_selectors:
            try:
                code_input = await self.page.wait_for_selector(selector, timeout=3000)
                if code_input:
                    await code_input.fill(code)
                    logger.info(f"已填入二次验证码: {code}")
                    break
            except Exception:
                continue

        await self.page.wait_for_timeout(500)
        await self._click_submit()
        await self.page.wait_for_timeout(2000)

    async def _handle_register_form(self, email: str, password: str, region: str):
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_timeout(3000)

        current_url = self.page.url
        logger.info(f"Filling form at: {current_url}")

        logger.info("填写邮箱...")
        email_selectors = [
            'input[type="email"]',
            'input[name*="email"]',
            'input[id*="email"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="Email"]',
            'input[placeholder*="mail"]',
        ]

        for selector in email_selectors:
            try:
                email_input = await self.page.wait_for_selector(selector, timeout=3000)
                if email_input:
                    await email_input.click()
                    await email_input.fill(email)
                    logger.info(f"已填入邮箱: {email}")
                    break
            except Exception:
                continue

        await self.page.wait_for_timeout(500)

        logger.info("填写密码...")
        password_inputs = await self.page.query_selector_all('input[type="password"]')
        logger.debug(f"找到 {len(password_inputs)} 个密码输入框")

        if password_inputs:
            await password_inputs[0].fill(password)
            logger.info("已填入密码")

        if len(password_inputs) >= 2:
            await password_inputs[1].fill(password)
            logger.info("已填入确认密码")

        await self.page.wait_for_timeout(500)

        await self._check_agreement()

        await self.page.wait_for_timeout(500)

        await self._click_submit()

    async def _check_agreement(self):
        try:
            checkboxes = await self.page.query_selector_all('input[type="checkbox"]')
            for checkbox in checkboxes:
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox.check()
                    logger.info("已勾选协议")
                    return
        except Exception:
            pass

    async def _click_submit(self) -> bool:
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("注册")',
            'button:has-text("确定")',
            'button:has-text("下一步")',
            'button:has-text("发送")',
            'button:has-text("立即注册")',
        ]

        for selector in submit_selectors:
            try:
                btn = await self.page.wait_for_selector(selector, timeout=2000)
                if btn:
                    is_visible = await btn.is_visible()
                    if is_visible:
                        await btn.click()
                        logger.info(f"已点击: {selector}")
                        return True
            except Exception:
                continue

        return False

    async def _check_for_captcha(self) -> bool:
        captcha_selectors = [
            'iframe[src*="captcha"]',
            'iframe[src*="verify"]',
            'iframe[src*="geetest"]',
            ".miverify",
        ]

        for selector in captcha_selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=2000)
                if element:
                    logger.info(f"检测到验证码: {selector}")
                    return True
            except Exception:
                continue

        return False

    async def _handle_email_verification_auto(self, email: str):
        logger.info("自动获取邮箱验证码...")

        await self.page.wait_for_timeout(3000)

        code = await self.mail_client.wait_for_verification_code(
            sender_pattern="xiaomi",
            timeout=300,
            poll_interval=3,
        )

        if not code:
            logger.warning("未自动获取到验证码, 等待人工输入...")
            await self._handle_email_verification_manual()
            return

        code_input_selectors = [
            'input[name*="code"]',
            'input[name*="verify"]',
            'input[id*="code"]',
            'input[placeholder*="验证"]',
            'input[type="text"]',
        ]

        for selector in code_input_selectors:
            try:
                code_input = await self.page.wait_for_selector(selector, timeout=3000)
                if code_input:
                    await code_input.fill(code)
                    logger.info(f"已填入验证码: {code}")
                    break
            except Exception:
                continue

        await self.page.wait_for_timeout(500)
        await self._click_submit()

    async def _handle_email_verification_manual(self):
        logger.info("等待人工输入验证码...")
        await self.captcha_handler.wait_for_manual_captcha("验证码")

    async def _wait_for_sts_callback(self, timeout: int = 120000) -> bool:
        logger.info("等待注册完成...")

        if "account.xiaomi.com/fe/service/account" in self.page.url:
            logger.info("当前已在账号页，直接跳转到 aistudio")
            await self.page.goto(
                "https://aistudio.xiaomimimo.com/#/",
                wait_until="networkidle",
                timeout=60000,
            )
            await self.page.wait_for_timeout(5000)
            return True

        try:
            await self.page.wait_for_url(
                "**/aistudio.xiaomimimo.com/**", timeout=timeout
            )
            logger.success(f"注册成功! 当前URL: {self.page.url}")
            return True
        except Exception:
            current_url = self.page.url

            if "aistudio.xiaomimimo.com" in current_url:
                logger.success(f"注册成功! 当前URL: {current_url}")
                return True

            if "verifyEmail" in current_url:
                logger.info("当前仍在 verifyEmail 页面，继续完成验证后跳转")
                if self.mail_client:
                    await self._handle_second_verification("")
                    await self.page.wait_for_timeout(2000)
                try:
                    await self.page.goto(
                        "https://aistudio.xiaomimimo.com/#/",
                        wait_until="networkidle",
                        timeout=60000,
                    )
                    return True
                except Exception:
                    pass

            if "account.xiaomi.com/fe/service/account" in current_url:
                logger.info("账号已创建, 正在跳转到 aistudio...")
                await self.page.goto(
                    "https://aistudio.xiaomimimo.com/#/",
                    wait_until="networkidle",
                    timeout=60000,
                )
                await self.page.wait_for_timeout(5000)
                return True

            logger.warning(f"当前URL: {current_url}")
            await self.captcha_handler.wait_for_manual_captcha("完成注册流程")

            return "aistudio.xiaomimimo.com" in self.page.url
