from playwright.async_api import Page
import asyncio
from src.utils.logger import get_logger

logger = get_logger()


class CaptchaHandler:
    def __init__(self, page: Page, wait_timeout: int = 300):
        self.page = page
        self.wait_timeout = wait_timeout

    async def wait_for_manual_captcha(self, description: str = "验证码") -> bool:
        logger.warning(f"需要人工处理: {description}")
        logger.info("请在浏览器中完成验证码操作...")

        print(f"\n{'=' * 60}")
        print(f"  请在浏览器中完成 {description} 操作")
        print(f"  等待时间: {self.wait_timeout} 秒")
        print(f"{'=' * 60}\n")

        for i in range(self.wait_timeout, 0, -1):
            print(f"\r  剩余时间: {i:3d} 秒", end="", flush=True)
            await asyncio.sleep(1)

        print("\n")
        logger.info("验证码等待时间结束")
        return True

    async def wait_for_captcha_iframe(self, timeout: int = 10000) -> bool:
        try:
            captcha_frame = self.page.frame_locator("iframe[src*='captcha']")
            if captcha_frame:
                logger.info("检测到验证码iframe")
                return True
        except Exception:
            pass
        return False

    async def handle_slider_captcha(self):
        await self.wait_for_manual_captcha("滑块验证码")

    async def handle_image_captcha(self):
        await self.wait_for_manual_captcha("图片验证码")

    async def handle_geetest_captcha(self):
        await self.wait_for_manual_captcha("极验验证码")

    async def wait_for_navigation_complete(
        self, target_url_substring: str, timeout: int = 30000
    ):
        logger.info(f"等待页面跳转到包含 '{target_url_substring}' 的URL...")

        try:
            await self.page.wait_for_url(
                f"**/*{target_url_substring}*", timeout=timeout
            )
            logger.info(f"已到达目标页面: {self.page.url}")
            return True
        except Exception as e:
            logger.error(f"等待页面跳转超时: {e}")
            return False

    async def wait_for_element(self, selector: str, timeout: int = 30000):
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def is_on_captcha_page(self) -> bool:
        current_url = self.page.url
        captcha_indicators = ["captcha", "verify", "geetest", "slider"]
        return any(indicator in current_url.lower() for indicator in captcha_indicators)
