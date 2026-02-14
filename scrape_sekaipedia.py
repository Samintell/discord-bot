"""
Scrape Sekaipedia's song list to generate a JSON mapping of
Japanese titles to English and/or Romaji translations.

Uses the MediaWiki API to:
1. Enumerate all pages in Category:Songs
2. Fetch the {{Infobox song}} wikitext for each page
3. Extract 'japanese', 'romaji', and 'english' fields
4. Output a JSON file mapping Japanese title -> {romaji, english}

Usage:
    python scrape_sekaipedia.py
    python scrape_sekaipedia.py --output sekaipedia_translations.json
    python scrape_sekaipedia.py --delay 0.5
"""

import argparse
import json
import re
import sys
import time
import requests

API_URL = "https://www.sekaipedia.org/w/api.php"
DEFAULT_OUTPUT = "sekaipedia_translations.json"
DEFAULT_DELAY = 0.3  # seconds between individual page requests

# Shared session with a proper User-Agent (bare requests gets 403'd)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "MaiMaiSongBot/1.0 (Discord quiz bot; scrape_sekaipedia.py)",
})


def get_all_song_pages():
    """Fetch all page titles in Category:Songs using the MediaWiki API."""
    pages = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Songs",
        "cmlimit": "500",  # max allowed per request
        "cmtype": "page",
        "format": "json",
    }

    print("Fetching song page list from Category:Songs...")
    while True:
        resp = SESSION.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        members = data.get("query", {}).get("categorymembers", [])
        for m in members:
            pages.append({"pageid": m["pageid"], "title": m["title"]})

        # Handle continuation for large categories
        cont = data.get("continue")
        if cont:
            params["cmcontinue"] = cont["cmcontinue"]
            print(f"  ...fetched {len(pages)} pages so far, continuing...")
        else:
            break

    print(f"Found {len(pages)} song pages total.")
    return pages


def fetch_infobox_wikitext(page_title):
    """Fetch section 0 wikitext (which contains the Infobox) for a page."""
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "section": "0",
        "format": "json",
    }
    resp = SESSION.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        return None

    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def parse_infobox_field(wikitext, field_name):
    """
    Extract a field value from an {{Infobox song}} template.
    Handles multi-line values and trims whitespace.
    """
    # Match '| field_name = value' on a single line first (most common),
    # where the value ends at the newline.
    # Use a word-boundary-like anchor to avoid partial field name matches.
    pattern = (
        r'^\|\s*'
        + re.escape(field_name)
        + r'\s*=\s*(.*?)$'
    )
    match = re.search(pattern, wikitext, re.MULTILINE | re.IGNORECASE)
    if match:
        value = match.group(1).strip()
        # Reject if the captured value looks like another template field
        if value.startswith('|'):
            return None
        # Remove any wiki markup like [[ ]] or {{ }}
        value = re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]', r'\2', value)
        # Clean up remaining markup
        value = re.sub(r'\{\{[^}]*\}\}', '', value)
        value = value.strip()
        return value if value else None
    return None


def scrape_translations(pages, delay=DEFAULT_DELAY):
    """
    For each song page, fetch the infobox and extract
    japanese, romaji, and english fields.

    Returns a dict mapping japanese_title -> {romaji, english, page_title}.
    """
    translations = {}
    total = len(pages)
    errors = []

    for i, page in enumerate(pages, 1):
        title = page["title"]
        if i % 50 == 0 or i == 1 or i == total:
            print(f"  Processing {i}/{total}: {title}")

        try:
            wikitext = fetch_infobox_wikitext(title)
            if not wikitext:
                errors.append({"page": title, "reason": "no wikitext returned"})
                continue

            # Only process pages that have an Infobox song
            if "Infobox song" not in wikitext and "infobox song" not in wikitext.lower():
                errors.append({"page": title, "reason": "no Infobox song found"})
                continue

            jp = parse_infobox_field(wikitext, "japanese")
            romaji = parse_infobox_field(wikitext, "romaji")
            english = parse_infobox_field(wikitext, "english")

            if jp:
                entry = {}
                if romaji:
                    entry["romaji"] = romaji
                if english:
                    entry["english"] = english
                entry["page_title"] = title

                if entry.get("romaji") or entry.get("english"):
                    translations[jp] = entry
            else:
                # Some pages may use the page title as the song name
                # and not have a separate japanese field (already in romaji)
                pass

        except requests.RequestException as e:
            errors.append({"page": title, "reason": str(e)})
            print(f"    ⚠ Error fetching {title}: {e}")
            # Back off on network errors
            time.sleep(2)
        except Exception as e:
            errors.append({"page": title, "reason": str(e)})

        # Rate-limit to be polite to the wiki
        if delay > 0:
            time.sleep(delay)

    if errors:
        print(f"\n⚠ {len(errors)} pages had issues:")
        for err in errors[:20]:
            print(f"    {err['page']}: {err['reason']}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")

    return translations


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Sekaipedia song translations (Japanese -> Romaji/English)"
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between API requests in seconds (default: {DEFAULT_DELAY})",
    )
    args = parser.parse_args()

    print("=== Sekaipedia Song Translation Scraper ===\n")

    # Step 1: Get all song pages
    pages = get_all_song_pages()
    if not pages:
        print("No song pages found. Exiting.")
        sys.exit(1)

    # Step 2: Scrape translations from each page
    print(f"\nScraping infobox data from {len(pages)} pages (delay={args.delay}s)...\n")
    translations = scrape_translations(pages, delay=args.delay)

    # Step 3: Write output
    print(f"\nExtracted {len(translations)} translations with Japanese titles.")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    print(f"Translations saved to {args.output}")

    # Show some sample entries
    print("\nSample entries:")
    for jp, data in list(translations.items())[:5]:
        print(f"  {jp} -> romaji={data.get('romaji', 'N/A')}, english={data.get('english', 'N/A')}")


if __name__ == "__main__":
    main()
