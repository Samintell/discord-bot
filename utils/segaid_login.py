"""
SEGA ID login flow for maimai NET (International).

Follows the same flow as tomomai (https://github.com/shedaniel/tomomai):
1. GET the auth gateway login page to obtain a JSESSIONID session cookie
2. POST the SEGA ID credentials to /common_auth/login/sid
3. On success the response sets the clal session cookie
"""

import re
import asyncio
import aiohttp
from urllib.parse import urlencode
from typing import Optional, Tuple

from utils.maimai_scraper import USER_AGENT, validate_token
from utils.segaid_db import get_segaid_account, save_token

AUTH_LOGIN_URL = "https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/"
SID_LOGIN_URL = "https://lng-tgk-aime-gw.am-all.net/common_auth/login/sid"

TIMEOUT = aiohttp.ClientTimeout(total=15)


def _headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


async def login_with_segaid(username: str, password: str) -> Tuple[bool, str, Optional[str]]:
    """Log in to maimai NET (International) using a SEGA ID username and password.

    Returns:
        (success, message, clal_cookie)
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Fetch the login page to obtain the JSESSIONID cookie
            async with session.get(
                AUTH_LOGIN_URL, headers=_headers(), allow_redirects=False, timeout=TIMEOUT
            ) as resp:
                set_cookies = resp.headers.getall("Set-Cookie", [])
                if resp.status not in (200, 302) or not set_cookies:
                    return False, f"Could not reach the SEGA ID login page (HTTP {resp.status}). Please try again later.", None

            # Step 2: POST credentials (session cookie jar follows automatically)
            params = urlencode({"retention": "1", "sid": username, "password": password})
            async with session.post(
                f"{SID_LOGIN_URL}?{params}", headers=_headers(), allow_redirects=False, timeout=TIMEOUT
            ) as resp:
                if resp.status != 302:
                    return False, "Login failed. Please check your SEGA ID username and password.", None

                # Step 3: Extract the clal cookie from Set-Cookie headers
                set_cookies = resp.headers.getall("Set-Cookie", [])
                for cookie_header in set_cookies:
                    match = re.search(r"clal=([^;]+)", cookie_header)
                    if match:
                        return True, "SEGA ID login successful", match.group(1)

                return False, "maimai accepted your credentials but did not return a session cookie. This is usually a temporary upstream issue. Please try again in a few minutes.", None

    except asyncio.TimeoutError:
        return False, "Connection timed out. maimai NET may be under maintenance (4AM-7AM JST).", None
    except aiohttp.ClientError as e:
        return False, f"Connection error: {e}", None


async def try_refresh_with_segaid(discord_user_id: str) -> Optional[str]:
    """If the user has saved SEGA ID credentials, re-login to get a fresh clal cookie.

    Returns the new clal cookie (already saved to the main database) or None.
    """
    try:
        account = await get_segaid_account(discord_user_id)
    except Exception:
        return None

    if not account:
        return None

    ok, _, clal = await login_with_segaid(account["username"], account["password"])
    if not ok or not clal:
        return None

    try:
        await save_token(discord_user_id, clal)
    except RuntimeError:
        return None

    # Confirm the session is valid
    is_valid, _, _ = await validate_token(clal)
    if not is_valid:
        return None

    return clal
