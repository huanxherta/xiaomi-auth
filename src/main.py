import argparse
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.temp_mail import TempMailClient
from src.browser import BrowserManager, CaptchaHandler
from src.auth import LoginHandler, RegisterHandler
from src.storage import CookieManager

logger = get_logger()


class XiaomiAuthClient:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config.load(config_path)
        self.browser_manager: Optional[BrowserManager] = None
        self.cookie_manager = CookieManager(self.config.storage.cookies_dir)
        self.mail_client: Optional[TempMailClient] = None

    async def login(self, account: str, password: str) -> bool:
        logger.info(f"开始登录: {account}")

        async with BrowserManager(self.config) as browser:
            self.browser_manager = browser
            page = await browser.get_page()

            captcha_handler = CaptchaHandler(
                page, wait_timeout=self.config.captcha.wait_timeout
            )

            login_handler = LoginHandler(page, self.config, captcha_handler)

            await login_handler.navigate_to_login()

            success = await login_handler.perform_login(account, password)

            if success:
                cookies = await browser.get_cookies()
                self.cookie_manager.save_cookies(cookies, account)
                logger.success(f"登录成功! Cookies已保存")
                return True
            else:
                logger.error("登录失败")
                return False

    async def register_with_temp_email(
        self,
        password: str,
        jwt_token: str = "12345678",
        api_url: str = "https://mailfree.hxnb.workers.dev",
    ) -> tuple[bool, Optional[str]]:
        logger.info("使用临时邮箱注册...")

        self.mail_client = TempMailClient(api_url=api_url, jwt_token=jwt_token)

        domains = await self.mail_client.get_domains()
        if domains:
            logger.info(f"可用域名: {domains}")

        email = await self.mail_client.generate_email()
        if not email:
            logger.error("创建临时邮箱失败")
            await self.mail_client.close()
            return False, None

        logger.success(f"临时邮箱: {email}")

        try:
            async with BrowserManager(self.config) as browser:
                self.browser_manager = browser
                page = await browser.get_page()

                captcha_handler = CaptchaHandler(
                    page, wait_timeout=self.config.captcha.wait_timeout
                )

                register_handler = RegisterHandler(
                    page, self.config, captcha_handler, mail_client=self.mail_client
                )

                await register_handler.navigate_to_register()

                success = await register_handler.perform_register(
                    email, password, auto_verify=True
                )

                if success:
                    await page.wait_for_timeout(2000)

                    auth_data = await self._extract_auth_data(page)

                    cookies = await browser.get_cookies()

                    self.cookie_manager.save_auth_data(
                        account=email,
                        service_token=auth_data.get("serviceToken"),
                        user_id=auth_data.get("userId"),
                        xiaomichatbot_ph=auth_data.get("xiaomichatbot_ph"),
                        cookies=cookies,
                        local_storage=auth_data.get("localStorage"),
                    )
                    logger.success(f"注册成功! 认证数据已保存")

                return success, email
        finally:
            await self.mail_client.close()

    async def _extract_auth_data(self, page) -> Dict[str, Any]:
        logger.info("提取认证数据...")

        auth_data = {}
        captured = {"xiaomichatbot_ph": None}

        def handle_request(request):
            try:
                url = request.url
                if (
                    "/open-apis/chat/conversation/list" in url
                    and "xiaomichatbot_ph=" in url
                ):
                    import re

                    match = re.search(r"xiaomichatbot_ph=([^&#]+)", url)
                    if match and not captured["xiaomichatbot_ph"]:
                        captured["xiaomichatbot_ph"] = match.group(1)
            except Exception:
                pass

        page.on("request", handle_request)

        try:
            await page.goto(
                "https://aistudio.xiaomimimo.com/open-apis/v1/genLoginUrl",
                wait_until="networkidle",
                timeout=60000,
            )
            await page.wait_for_timeout(8000)
        except Exception as e:
            logger.debug(f"走 aistudio 登录链路失败: {e}")

        try:
            local_storage = await page.evaluate("() => JSON.stringify(localStorage)")
            local_storage = json.loads(local_storage) if local_storage else {}
            auth_data["localStorage"] = local_storage

            for key in [
                "serviceToken",
                "userId",
                "xiaomichatbot_ph",
                "token",
                "user_id",
                "uid",
            ]:
                if key in local_storage:
                    auth_data[key] = local_storage[key]
                    logger.debug(f"从localStorage获取 {key}")
        except Exception as e:
            logger.debug(f"读取localStorage失败: {e}")

        try:
            if "serviceToken" not in auth_data:
                service_token = await page.evaluate("""
                    () => {
                        const cookies = document.cookie.split(';');
                        for (const cookie of cookies) {
                            const [name, value] = cookie.trim().split('=');
                            if (name === 'serviceToken') return value;
                        }
                        return null;
                    }
                """)
                if service_token:
                    auth_data["serviceToken"] = service_token
                    logger.debug("从cookie获取 serviceToken")
        except Exception as e:
            logger.debug(f"读取cookie失败: {e}")

        try:
            all_cookies = await page.context.cookies()
            for cookie in all_cookies:
                name = cookie.get("name")
                value = cookie.get("value")
                if name == "serviceToken" and value and "serviceToken" not in auth_data:
                    auth_data["serviceToken"] = value
                if name == "userId" and value and "userId" not in auth_data:
                    auth_data["userId"] = value
                if (
                    name == "xiaomichatbot_ph"
                    and value
                    and "xiaomichatbot_ph" not in auth_data
                ):
                    auth_data["xiaomichatbot_ph"] = value
        except Exception as e:
            logger.debug(f"读取 context cookies 失败: {e}")

        if captured["xiaomichatbot_ph"] and "xiaomichatbot_ph" not in auth_data:
            auth_data["xiaomichatbot_ph"] = captured["xiaomichatbot_ph"]

        try:
            session_storage = await page.evaluate(
                "() => JSON.stringify(sessionStorage)"
            )
            session_storage = json.loads(session_storage) if session_storage else {}
            auth_data["sessionStorage"] = session_storage
            if (
                "xiaomichatbot_ph" in session_storage
                and "xiaomichatbot_ph" not in auth_data
            ):
                auth_data["xiaomichatbot_ph"] = session_storage["xiaomichatbot_ph"]
        except Exception as e:
            logger.debug(f"读取sessionStorage失败: {e}")

        try:
            current_url = page.url
            if "userId=" in current_url and "userId" not in auth_data:
                import re

                match = re.search(r"userId=([^&#]+)", current_url)
                if match:
                    auth_data["userId"] = match.group(1)
        except Exception:
            pass

        logger.info(f"提取到认证数据: {list(auth_data.keys())}")
        return auth_data

    async def register(
        self, email: str, password: str, region: str = "TW", auto_verify: bool = False
    ) -> bool:
        logger.info(f"开始注册: {email}")

        async with BrowserManager(self.config) as browser:
            self.browser_manager = browser
            page = await browser.get_page()

            captcha_handler = CaptchaHandler(
                page, wait_timeout=self.config.captcha.wait_timeout
            )

            register_handler = RegisterHandler(
                page, self.config, captcha_handler, mail_client=self.mail_client
            )

            await register_handler.navigate_to_register()

            success = await register_handler.perform_register(
                email, password, region, auto_verify=auto_verify
            )

            if success:
                cookies = await browser.get_cookies()
                self.cookie_manager.save_cookies(cookies, email)
                logger.success(f"注册成功! Cookies已保存")
                return True
            else:
                logger.error("注册失败")
                return False

    async def refresh_auth_data(self, account: str) -> bool:
        logger.info(f"刷新认证数据: {account}")

        saved = self.cookie_manager.load_auth_data(account)
        if not saved or not saved.get("cookies"):
            logger.error("未找到已保存 cookies")
            return False

        async with BrowserManager(self.config) as browser:
            self.browser_manager = browser
            page = await browser.get_page()
            await browser.set_cookies(saved["cookies"])

            auth_data = await self._extract_auth_data(page)

            self.cookie_manager.save_auth_data(
                account=account,
                service_token=auth_data.get("serviceToken")
                or saved.get("auth", {}).get("serviceToken"),
                user_id=auth_data.get("userId") or saved.get("auth", {}).get("userId"),
                xiaomichatbot_ph=auth_data.get("xiaomichatbot_ph")
                or saved.get("auth", {}).get("xiaomichatbot_ph"),
                cookies=await browser.get_cookies(),
                local_storage=auth_data.get("localStorage"),
            )
            logger.success("认证数据刷新完成")
            return True

    def load_cookies(self, account: str):
        return self.cookie_manager.load_cookies(account)

    def load_auth_data(self, account: str):
        return self.cookie_manager.load_auth_data(account)

    def list_accounts(self):
        return self.cookie_manager.list_saved_accounts()


async def main():
    parser = argparse.ArgumentParser(
        description="小米账号登录/注册自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 登录
  python -m src.main login -a your@email.com -p yourpassword
  
  # 使用临时邮箱注册
  python -m src.main register-temp -p yourpassword
  
  # 使用指定邮箱注册  
  python -m src.main register -e new@email.com -p yourpassword
  
  # 列出已保存的账号
  python -m src.main list
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    login_parser = subparsers.add_parser("login", help="登录小米账号")
    login_parser.add_argument("-a", "--account", required=True, help="账号(邮箱/手机)")
    login_parser.add_argument("-p", "--password", required=True, help="密码")

    register_parser = subparsers.add_parser("register", help="注册新账号")
    register_parser.add_argument("-e", "--email", required=True, help="邮箱地址")
    register_parser.add_argument("-p", "--password", required=True, help="密码")
    register_parser.add_argument("-r", "--region", default="TW", help="地区(TW/CN等)")

    temp_register_parser = subparsers.add_parser(
        "register-temp", help="使用临时邮箱注册"
    )
    temp_register_parser.add_argument("-p", "--password", required=True, help="密码")
    temp_register_parser.add_argument(
        "--jwt", default="12345678", help="邮箱API JWT Token"
    )
    temp_register_parser.add_argument(
        "--api", default="https://mailfree.hxnb.workers.dev", help="邮箱API URL"
    )

    refresh_parser = subparsers.add_parser(
        "refresh-auth", help="用已保存 cookies 刷新认证数据"
    )
    refresh_parser.add_argument("-a", "--account", required=True, help="账号邮箱")

    subparsers.add_parser("list", help="列出已保存的账号")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    client = XiaomiAuthClient()

    if args.command == "login":
        success = await client.login(args.account, args.password)
        exit(0 if success else 1)

    elif args.command == "register":
        success = await client.register(args.email, args.password, args.region)
        exit(0 if success else 1)

    elif args.command == "register-temp":
        success, email = await client.register_with_temp_email(
            password=args.password, jwt_token=args.jwt, api_url=args.api
        )
        if success and email:
            print(f"\n{'=' * 50}")
            print(f"  注册成功!")
            print(f"  邮箱: {email}")
            auth_data = client.load_auth_data(email)
            if auth_data and auth_data.get("auth"):
                print(f"  serviceToken: {auth_data['auth'].get('serviceToken', 'N/A')}")
                print(f"  userId: {auth_data['auth'].get('userId', 'N/A')}")
                print(
                    f"  xiaomichatbot_ph: {auth_data['auth'].get('xiaomichatbot_ph', 'N/A')}"
                )
            print(f"{'=' * 50}")
        exit(0 if success else 1)

    elif args.command == "refresh-auth":
        success = await client.refresh_auth_data(args.account)
        if success:
            auth_data = client.load_auth_data(args.account)
            if auth_data and auth_data.get("auth"):
                print(f"serviceToken: {auth_data['auth'].get('serviceToken')}")
                print(f"userId: {auth_data['auth'].get('userId')}")
                print(f"xiaomichatbot_ph: {auth_data['auth'].get('xiaomichatbot_ph')}")
        exit(0 if success else 1)

    elif args.command == "list":
        accounts = client.list_accounts()
        if accounts:
            print("\n已保存的账号:")
            for acc in accounts:
                print(f"  - {acc}")
        else:
            print("\n暂无已保存的账号")


if __name__ == "__main__":
    asyncio.run(main())
