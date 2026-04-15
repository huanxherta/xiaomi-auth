import aiohttp
import asyncio
import re
from typing import Optional, List
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class Email:
    id: int
    sender: str
    subject: str
    content: str
    html_content: str
    verification_code: Optional[str]
    received_at: str
    is_read: int


class TempMailClient:
    def __init__(
        self,
        api_url: str = "https://mailfree.hxnb.workers.dev",
        jwt_token: str = "12345678",
    ):
        self.api_url = api_url.rstrip("/")
        self.jwt_token = jwt_token
        self.email_address: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "Authorization": f"Bearer {self.jwt_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_domains(self) -> List[str]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.api_url}/api/domains") as resp:
                if resp.status == 200:
                    domains = await resp.json()
                    logger.debug(f"Available domains: {domains}")
                    return domains
                return []
        except Exception as e:
            logger.error(f"Error getting domains: {e}")
            return []

    async def generate_email(
        self, length: int = 8, domain_index: int = 0
    ) -> Optional[str]:
        try:
            session = await self._get_session()
            url = f"{self.api_url}/api/generate?length={length}&domainIndex={domain_index}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.email_address = data.get("email")
                    logger.success(f"Generated temp email: {self.email_address}")
                    return self.email_address
                else:
                    text = await resp.text()
                    logger.error(f"Failed to generate email: {resp.status} - {text}")
                    return None
        except Exception as e:
            logger.error(f"Error generating email: {e}")
            return None

    async def create_email(self, local: str, domain_index: int = 0) -> Optional[str]:
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.api_url}/api/create",
                json={"local": local, "domainIndex": domain_index},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.email_address = data.get("email")
                    logger.success(f"Created temp email: {self.email_address}")
                    return self.email_address
                else:
                    text = await resp.text()
                    logger.error(f"Failed to create email: {resp.status} - {text}")
                    return None
        except Exception as e:
            logger.error(f"Error creating email: {e}")
            return None

    async def get_emails(self, mailbox: str = None, limit: int = 20) -> List[Email]:
        mailbox = mailbox or self.email_address
        if not mailbox:
            logger.warning("No mailbox specified")
            return []

        try:
            session = await self._get_session()
            url = f"{self.api_url}/api/emails?mailbox={mailbox}&limit={limit}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    emails = []
                    for item in data:
                        emails.append(
                            Email(
                                id=item.get("id", 0),
                                sender=item.get("sender", ""),
                                subject=item.get("subject", ""),
                                content=item.get("preview", ""),
                                html_content="",
                                verification_code=item.get("verification_code"),
                                received_at=item.get("received_at", ""),
                                is_read=item.get("is_read", 0),
                            )
                        )
                    return emails
                return []
        except Exception as e:
            logger.error(f"Error getting emails: {e}")
            return []

    async def get_email_detail(self, email_id: int) -> Optional[Email]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.api_url}/api/email/{email_id}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return Email(
                        id=data.get("id", 0),
                        sender=data.get("sender", ""),
                        subject=data.get("subject", ""),
                        content=data.get("content", ""),
                        html_content=data.get("html_content", ""),
                        verification_code=data.get("verification_code"),
                        received_at=data.get("received_at", ""),
                        is_read=data.get("is_read", 0),
                    )
                return None
        except Exception as e:
            logger.error(f"Error getting email detail: {e}")
            return None

    async def wait_for_verification_code(
        self,
        sender_pattern: str = None,
        subject_pattern: str = None,
        timeout: int = 180,
        poll_interval: int = 5,
    ) -> Optional[str]:
        logger.info(f"Waiting for verification code (timeout: {timeout}s)...")

        for elapsed in range(0, timeout, poll_interval):
            emails = await self.get_emails()

            for email in emails:
                if (
                    sender_pattern
                    and sender_pattern.lower() not in email.sender.lower()
                ):
                    continue

                if (
                    subject_pattern
                    and subject_pattern.lower() not in email.subject.lower()
                ):
                    continue

                if email.verification_code:
                    logger.success(
                        f"Found verification code in list: {email.verification_code}"
                    )
                    return email.verification_code

                detail = await self.get_email_detail(email.id)
                if detail:
                    code = self._extract_code(detail.content) or self._extract_code(
                        detail.html_content
                    )
                    if code:
                        logger.success(f"Found verification code: {code}")
                        return code

            remaining = timeout - elapsed
            logger.debug(f"No verification email yet ({remaining}s remaining)")
            await asyncio.sleep(poll_interval)

        logger.warning("Timeout waiting for verification email")
        return None

    def _extract_code(self, body: str) -> Optional[str]:
        if not body:
            return None

        patterns = [
            r"验证码[：:\s]*([A-Za-z0-9]{4,8})",
            r"码[：:\s]*([A-Za-z0-9]{4,8})",
            r"code[：:\s]*([A-Za-z0-9]{4,8})",
            r"Code[：:\s]*([A-Za-z0-9]{4,8})",
            r"verification code[：:\s]*([A-Za-z0-9]{4,8})",
            r">\s*([A-Za-z0-9]{6})\s*<",
            r"\b([0-9]{6})\b",
            r"\b([A-Z0-9]{6})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                code = match.group(1)
                if len(code) >= 4 and len(code) <= 8:
                    return code

        return None


async def test_api():
    client = TempMailClient(jwt_token="12345678")

    print("Testing temp mail API...")

    domains = await client.get_domains()
    print(f"Domains: {domains}")

    email = await client.generate_email()
    print(f"Email: {email}")

    if email:
        emails = await client.get_emails()
        print(f"Inbox count: {len(emails)}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(test_api())
