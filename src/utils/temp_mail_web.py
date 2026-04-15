from playwright.async_api import Page, BrowserContext
import asyncio
import re
from typing import Optional, List
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class Email:
    id: str
    from_addr: str
    subject: str
    body: str


class TempMailWebClient:
    def __init__(
        self, page: Page, mail_url: str = "https://mailfree.hxnb.workers.dev/"
    ):
        self.page = page
        self.mail_url = mail_url
        self.email_address: Optional[str] = None

    async def create_email(self) -> Optional[str]:
        logger.info(f"Navigating to temp mail: {self.mail_url}")

        await self.page.goto(self.mail_url, wait_until="networkidle", timeout=60000)
        await self.page.wait_for_timeout(2000)

        email_selectors = [
            ".email-address",
            "#email",
            '[class*="email"]',
            ".mail-address",
            "input[readonly]",
            'input[type="text"]:visible',
        ]

        for selector in email_selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=5000)
                if element:
                    text = await element.inner_text()
                    if text and "@" in text:
                        self.email_address = text.strip()
                        logger.success(f"Found email address: {self.email_address}")
                        return self.email_address

                    value = await element.get_attribute("value")
                    if value and "@" in value:
                        self.email_address = value.strip()
                        logger.success(f"Found email address: {self.email_address}")
                        return self.email_address
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")

        await self.page.wait_for_timeout(1000)

        page_content = await self.page.content()
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        matches = re.findall(email_pattern, page_content)

        for match in matches:
            if "hxnb" in match or "mail" in match.lower():
                continue
            self.email_address = match
            logger.success(f"Found email from page: {self.email_address}")
            return self.email_address

        logger.warning("Could not find email address on temp mail page")

        try:
            create_btn_selectors = [
                'button:has-text("创建")',
                'button:has-text("新建")',
                'button:has-text("获取")',
                ".create-btn",
                "#create-email",
            ]

            for selector in create_btn_selectors:
                try:
                    btn = await self.page.wait_for_selector(selector, timeout=2000)
                    if btn:
                        await btn.click()
                        await self.page.wait_for_timeout(2000)
                        return await self.create_email()
                except Exception:
                    continue
        except Exception:
            pass

        return None

    async def refresh_inbox(self):
        try:
            refresh_selectors = [
                'button:has-text("刷新")',
                'button:has-text("Refresh")',
                ".refresh-btn",
                '[class*="refresh"]',
            ]

            for selector in refresh_selectors:
                try:
                    btn = await self.page.wait_for_selector(selector, timeout=2000)
                    if btn:
                        await btn.click()
                        await self.page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

            await self.page.reload(wait_until="networkidle")
            await self.page.wait_for_timeout(2000)
        except Exception as e:
            logger.debug(f"Refresh failed: {e}")

    async def get_latest_email(self) -> Optional[Email]:
        try:
            email_item_selectors = [
                ".email-item",
                ".mail-item",
                "tr:has(td)",
                '[class*="inbox"] > div',
                ".email-list > div",
            ]

            for selector in email_item_selectors:
                try:
                    items = await self.page.query_selector_all(selector)
                    if items:
                        first_item = items[0]
                        await first_item.click()
                        await self.page.wait_for_timeout(1000)

                        from_addr = ""
                        subject = ""
                        body = ""

                        try:
                            from_elem = await self.page.query_selector(
                                '.email-from, [class*="from"]'
                            )
                            if from_elem:
                                from_addr = await from_elem.inner_text()
                        except Exception:
                            pass

                        try:
                            subject_elem = await self.page.query_selector(
                                '.email-subject, [class*="subject"]'
                            )
                            if subject_elem:
                                subject = await subject_elem.inner_text()
                        except Exception:
                            pass

                        try:
                            body_elem = await self.page.query_selector(
                                '.email-body, [class*="body"], iframe'
                            )
                            if body_elem:
                                tag = await body_elem.evaluate("el => el.tagName")
                                if tag == "IFRAME":
                                    frame = self.page.frame_locator("iframe").first
                                    body = await frame.locator("body").inner_text()
                                else:
                                    body = await body_elem.inner_text()
                        except Exception:
                            pass

                        return Email(
                            id="1",
                            from_addr=from_addr.strip(),
                            subject=subject.strip(),
                            body=body.strip(),
                        )
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Get email failed: {e}")

        return None

    async def wait_for_verification_code(
        self,
        sender_pattern: str = None,
        subject_pattern: str = None,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> Optional[str]:
        logger.info(f"Waiting for verification email (timeout: {timeout}s)...")

        for elapsed in range(0, timeout, poll_interval):
            await self.refresh_inbox()

            email = await self.get_latest_email()

            if email and email.body:
                logger.debug(f"Checking email from: {email.from_addr}")

                if (
                    sender_pattern
                    and sender_pattern.lower() not in email.from_addr.lower()
                ):
                    await self.page.wait_for_timeout(poll_interval * 1000)
                    continue

                if (
                    subject_pattern
                    and subject_pattern.lower() not in email.subject.lower()
                ):
                    await self.page.wait_for_timeout(poll_interval * 1000)
                    continue

                code = self._extract_code(email.body)
                if code:
                    logger.success(f"Found verification code: {code}")
                    return code

            remaining = timeout - elapsed
            logger.info(
                f"No verification email yet, waiting... ({remaining}s remaining)"
            )
            await self.page.wait_for_timeout(poll_interval * 1000)

        logger.warning("Timeout waiting for verification email")
        return None

    def _extract_code(self, body: str) -> Optional[str]:
        patterns = [
            r"验证码[：:\s]*([A-Za-z0-9]{4,8})",
            r"码[：:\s]*([A-Za-z0-9]{4,8})",
            r"code[：:\s]*([A-Za-z0-9]{4,8})",
            r"Code[：:\s]*([A-Za-z0-9]{4,8})",
            r"verification code[：:\s]*([A-Za-z0-9]{4,8})",
            r">\s*([A-Za-z0-9]{6})\s*<",
            r"\b([0-9]{6})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1)

        return None
