from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger()


class BrowserManager:
    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> Page:
        logger.info("Starting browser...")

        if self.config.browser.engine == "camoufox":
            await self._start_camoufox()
        else:
            await self._start_chromium()

        self._page = await self._context.new_page()
        logger.info("Browser started successfully")

        return self._page

    async def _start_chromium(self):
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=self.config.browser.headless,
            slow_mo=self.config.browser.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        )

        self._context = await self._browser.new_context(
            viewport={
                "width": self.config.browser.viewport_width,
                "height": self.config.browser.viewport_height,
            },
            user_agent=self.config.browser.user_agent,
            locale=self.config.browser.locale,
            timezone_id=self.config.browser.timezone,
        )

        await self._inject_stealth_scripts()

    async def _start_camoufox(self):
        try:
            from camoufox.async_api import AsyncCamoufox
        except Exception as e:
            logger.warning(f"Camoufox not available, fallback to chromium: {e}")
            await self._start_chromium()
            return

        self._playwright = AsyncCamoufox(
            headless=self.config.browser.headless,
            os="linux",
        )
        launched = await self._playwright.__aenter__()

        if isinstance(launched, BrowserContext):
            self._browser = None
            self._context = launched
        else:
            self._browser = launched
            self._context = await self._browser.new_context(
                viewport={
                    "width": self.config.browser.viewport_width,
                    "height": self.config.browser.viewport_height,
                },
                locale=self.config.browser.locale,
                timezone_id=self.config.browser.timezone,
            )

    async def _inject_stealth_scripts(self):
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-TW', 'zh', 'en'],
            });
            
            window.chrome = {
                runtime: {},
            };
            
            Object.defineProperty(navigator, 'permissions', {
                get: () => ({
                    query: () => Promise.resolve({ state: 'granted' }),
                }),
            });
        """)

    async def get_page(self) -> Page:
        if self._page is None:
            await self.start()
        return self._page

    async def get_cookies(self):
        if self._context is None:
            raise RuntimeError("Browser context not initialized")
        return await self._context.cookies()

    async def set_cookies(self, cookies):
        if self._context is None:
            raise RuntimeError("Browser context not initialized")
        await self._context.add_cookies(cookies)

    async def close(self):
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            stop = getattr(self._playwright, "stop", None)
            if callable(stop):
                await stop()
            else:
                aexit = getattr(self._playwright, "__aexit__", None)
                if callable(aexit):
                    await aexit(None, None, None)
        logger.info("Browser closed")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
