"""
maimai NET (International) score scraper.
Fetches and parses user play data from maimaidx-eng.com.
"""

import re
import asyncio
import unicodedata
import aiohttp
import yarl
from urllib.parse import unquote
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from utils.song_loader import _get_all_songs
from utils.constants import SCORE_DIFFICULTY_NAMES

BASE_URL = "https://maimaidx-eng.com"
AUTH_LOGIN_URL = "https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/"
PLAYER_DATA_URL = f"{BASE_URL}/maimai-mobile/playerData/"
SCORES_URL = f"{BASE_URL}/maimai-mobile/record/musicGenre/search/?genre=99&diff="

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# CSS selectors for each difficulty's score background
DIFFICULTY_SELECTORS = [
    ".music_basic_score_back",
    ".music_advanced_score_back",
    ".music_expert_score_back",
    ".music_master_score_back",
    ".music_remaster_score_back",
]


def _normalize_name(name: str) -> str:
    """Normalize a song name for matching purposes."""
    # Unicode NFKC normalization (converts fullwidth chars, etc.)
    name = unicodedata.normalize("NFKC", name)
    # Strip whitespace
    name = name.strip()
    return name


def _build_song_index() -> Dict[str, List[Dict]]:
    """Build a lookup index from output.json for matching scraped song names.

    Returns:
        Dict mapping normalized title -> list of song entries from output.json
    """
    all_songs = _get_all_songs()
    index: Dict[str, List[Dict]] = {}

    for song in all_songs:
        title = song.get("title", "")
        if not title:
            continue
        key = _normalize_name(title)
        if key not in index:
            index[key] = []
        index[key].append(song)

    return index


def _find_song_id(
    song_name: str,
    chart_type: str,
    difficulty: str,
    index: Dict[str, List[Dict]],
) -> Optional[str]:
    """Try to match a scraped song name to a song_id from output.json.

    Matching strategy:
    1. Exact normalized match on title
    2. If multiple entries share the same title, prefer matching chart_type and difficulty
    """
    key = _normalize_name(song_name)
    entries = index.get(key)
    if not entries:
        return None

    # All entries with this title share the same song_id
    # (output.json has multiple entries per song for different difficulties/types)
    return entries[0].get("song_id")


async def validate_token(cookie: str) -> Tuple[bool, str]:
    """Check if a maimai NET clal cookie is valid and get session cookies.

    Uses the same flow as tomomai:
    1. Send clal cookie to auth gateway login
    2. 302 redirect = valid (follow to get maimaidx-eng.com session)
    3. 200 = token expired

    Returns:
        (is_valid, message) tuple
    """
    try:
        # Clean the cookie value
        clean_cookie = cookie.strip()
        # Try URL decoding in case it was copied encoded
        try:
            decoded = unquote(clean_cookie)
            if decoded != clean_cookie:
                clean_cookie = decoded
        except Exception:
            pass

        # Use headers that mimic a real browser
        headers = {
            "Cookie": f"clal={clean_cookie}",
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with aiohttp.ClientSession() as session:
            # Step 1: Check auth gateway with clal cookie (don't follow redirects)
            async with session.get(
                AUTH_LOGIN_URL, headers=headers, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    # Got login page = token is invalid/expired
                    return False, "Token is invalid or expired. Please log in to maimai NET and get a fresh clal cookie."

                if resp.status != 302:
                    return False, f"Unexpected response from auth server (HTTP {resp.status})"

                # Token is valid - get redirect location and cookies
                redirect_url = resp.headers.get("Location", "")
                # Extract any Set-Cookie headers
                cookies_from_redirect = resp.cookies

            # Step 2: Follow redirect to maimaidx-eng.com to establish session
            # Build cookie header from the clal and any cookies from redirect
            session_cookies = {"clal": clean_cookie}
            for cookie_name, cookie_morsel in cookies_from_redirect.items():
                session_cookies[cookie_name] = cookie_morsel.value

            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in session_cookies.items())

            # Follow the redirect chain to get maimaidx-eng.com session
            async with session.get(
                redirect_url if redirect_url else PLAYER_DATA_URL,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                final_url = str(resp.url)
                html = await resp.text()

                if resp.status != 200:
                    return False, f"HTTP {resp.status} after redirect - URL: {final_url[:60]}"

                if "error" in final_url.lower():
                    return False, f"Redirected to error page: {final_url[:60]}"

                if "ERROR CODE" in html or "Please login" in html:
                    return False, "Session could not be established - token may be invalid"

                # Try to get player data page
                async with session.get(
                    PLAYER_DATA_URL,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as player_resp:
                    player_html = await player_resp.text()
                    soup = BeautifulSoup(player_html, "html.parser")
                    name_el = soup.select_one(".name_block")

                    if not name_el:
                        title_el = soup.select_one("title")
                        page_title = title_el.get_text(strip=True) if title_el else "Unknown"
                        return False, f"Could not find player name. Page: '{page_title}'"

                    player_name = name_el.get_text(strip=True)
                    return True, f"Logged in as **{player_name}**"

    except asyncio.TimeoutError:
        return False, "Connection timed out. maimai NET may be under maintenance (4AM-7AM JST)."
    except aiohttp.ClientError as e:
        return False, f"Connection error: {e}"


async def fetch_all_scores(
    cookie: str,
    difficulties: Optional[List[int]] = None,
    on_progress=None,
) -> List[Dict]:
    """Fetch score data from maimai NET for all specified difficulties.

    Args:
        cookie: The clal cookie value from auth gateway
        difficulties: List of difficulty indices (0-4). Defaults to all [0,1,2,3,4].
        on_progress: Optional async callback(difficulty_name, count) called after each difficulty

    Returns:
        List of score dicts with keys: song_name, chart_type, difficulty, level,
        achievement, dx_score, fc, fs
    """
    if difficulties is None:
        difficulties = [0, 1, 2, 3, 4]

    all_scores: List[Dict] = []

    async with aiohttp.ClientSession() as session:
        # First, authenticate through the auth gateway to establish session
        headers = {
            "Cookie": f"clal={cookie}",
            "User-Agent": USER_AGENT,
        }

        async with session.get(
            AUTH_LOGIN_URL, headers=headers, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 302:
                print(f"Auth failed: HTTP {resp.status}")
                return []

            redirect_url = resp.headers.get("Location", "")

        # Follow redirect to establish maimaidx-eng.com session
        async with session.get(
            redirect_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"Failed to establish session: HTTP {resp.status}")
                return []

        # Now fetch scores using the established session
        for diff_idx in difficulties:
            url = f"{SCORES_URL}{diff_idx}"
            try:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        print(f"Failed to fetch difficulty {diff_idx}: HTTP {resp.status}")
                        continue

                    html = await resp.text()
                    scores = _parse_score_page(html, diff_idx)
                    all_scores.extend(scores)

                    if on_progress:
                        diff_name = SCORE_DIFFICULTY_NAMES[diff_idx] if diff_idx < len(SCORE_DIFFICULTY_NAMES) else str(diff_idx)
                        await on_progress(diff_name, len(scores))

            except asyncio.TimeoutError:
                print(f"Timeout fetching difficulty {diff_idx}")
            except aiohttp.ClientError as e:
                print(f"Error fetching difficulty {diff_idx}: {e}")

            # Small delay between requests to be polite
            if diff_idx != difficulties[-1]:
                await asyncio.sleep(0.5)

    return all_scores


def _parse_score_page(html: str, difficulty: int) -> List[Dict]:
    """Parse a maimai NET score page and extract score data.

    Args:
        html: Raw HTML from the score page
        difficulty: Difficulty index (0=basic, 1=advanced, 2=expert, 3=master, 4=remaster)

    Returns:
        List of score dicts
    """
    soup = BeautifulSoup(html, "html.parser")

    if difficulty >= len(DIFFICULTY_SELECTORS):
        return []

    selector = DIFFICULTY_SELECTORS[difficulty]
    blocks = soup.select(selector)
    scores: List[Dict] = []

    difficulty_name = SCORE_DIFFICULTY_NAMES[difficulty] if difficulty < len(SCORE_DIFFICULTY_NAMES) else "unknown"

    for block in blocks:
        try:
            # Check if the song has been played (has score blocks)
            score_blocks = block.select(".music_score_block")
            if not score_blocks:
                continue  # Unplayed song

            parent = block.parent

            # Extract chart type (dx/std) from icon
            icon_el = parent.select_one("img.music_kind_icon") if parent else None
            if not icon_el:
                continue
            icon_src = icon_el.get("src", "")
            if "music_dx.png" in icon_src:
                chart_type = "dx"
            elif "music_standard.png" in icon_src:
                chart_type = "std"
            else:
                continue

            # Extract song name
            name_el = block.select_one(".music_name_block")
            if not name_el:
                continue
            song_name = name_el.get_text(strip=True)

            # Extract level
            level_el = block.select_one(".music_lv_block")
            level = level_el.get_text(strip=True) if level_el else "?"

            # Extract achievement score
            if len(score_blocks) < 2:
                continue

            achievement_text = score_blocks[0].get_text(strip=True)
            achievement_match = re.search(r"(\d+\.?\d*)%", achievement_text)
            if not achievement_match:
                continue
            achievement_float = float(achievement_match.group(1))
            achievement = round(achievement_float * 10000)

            # Extract DX score
            dx_score_text = score_blocks[1].get_text(strip=True)
            dx_score_match = re.search(r"(\d+)\s*/\s*\d+", dx_score_text)
            dx_score = int(dx_score_match.group(1)) if dx_score_match else 0

            # Extract FC and FS status from h_30 images
            h30_elements = block.select(".h_30")
            fc = "none"
            fs = "none"

            if len(h30_elements) >= 2:
                # First h_30 = FS (sync) status
                fs_src = h30_elements[0].get("src", "")
                if "_fdxp.png" in fs_src:
                    fs = "fdx+"
                elif "_fdx.png" in fs_src:
                    fs = "fdx"
                elif "_fsp.png" in fs_src:
                    fs = "fs+"
                elif "_fs.png" in fs_src:
                    fs = "fs"
                elif "_sync.png" in fs_src:
                    fs = "sync"

                # Second h_30 = FC status
                fc_src = h30_elements[1].get("src", "")
                if "_app.png" in fc_src:
                    fc = "ap+"
                elif "_ap.png" in fc_src:
                    fc = "ap"
                elif "_fcp.png" in fc_src:
                    fc = "fc+"
                elif "_fc.png" in fc_src:
                    fc = "fc"

            scores.append({
                "song_name": song_name,
                "chart_type": chart_type,
                "difficulty": difficulty_name,
                "level": level,
                "achievement": achievement,
                "dx_score": dx_score,
                "fc": fc,
                "fs": fs,
            })

        except Exception as e:
            print(f"Error parsing score block: {e}")
            continue

    return scores


def match_scores_to_songs(scores: List[Dict]) -> Tuple[List[Dict], int]:
    """Match scraped scores to song_ids from output.json.

    Args:
        scores: List of score dicts from fetch_all_scores()

    Returns:
        (matched_scores, unmatched_count) tuple.
        matched_scores have an additional 'song_id' key.
    """
    index = _build_song_index()
    matched: List[Dict] = []
    unmatched = 0

    for score in scores:
        song_id = _find_song_id(
            score["song_name"],
            score["chart_type"],
            score["difficulty"],
            index,
        )
        if song_id:
            matched.append({**score, "song_id": song_id})
        else:
            unmatched += 1

    return matched, unmatched
