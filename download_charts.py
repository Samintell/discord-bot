"""
Script to download and process chart data from the Maichart-Converts GitHub repository.
Extracts Master and Re:Master simai chart data for use in chart quiz mode.
"""

import json
import os
import re
import subprocess
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Fix Windows console encoding for Japanese characters
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configuration
PROJECT_ROOT = Path(__file__).parent
CHARTS_DIR = PROJECT_ROOT / "charts"
REPO_URL = "https://github.com/Neskol/Maichart-Converts.git"
CLONE_DIR = PROJECT_ROOT / "_maichart_repo"
OUTPUT_JSON = PROJECT_ROOT / "output.json"
CHART_INDEX_FILE = CHARTS_DIR / "chart_index.json"
UNMATCHED_FILE = CHARTS_DIR / "unmatched.json"

# Category folders in the repo
REPO_CATEGORIES = [
    "maimai",
    "POPSアニメ",
    "niconicoボーカロイド",
    "オンゲキCHUNITHM",
    "ゲームバラエティ",
    "宴会場",
    "東方Project",
]


def clone_or_pull_repo() -> bool:
    """Clone the Maichart-Converts repo or pull if already cloned."""
    if CLONE_DIR.exists():
        print("Repository already cloned, pulling latest...")
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=str(CLONE_DIR),
                capture_output=True,
                text=True,
                timeout=120,
            )
            print("Pull complete.")
            return True
        except Exception as e:
            print(f"Error pulling: {e}")
            return False
    else:
        print(f"Cloning {REPO_URL} (shallow clone)...")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, str(CLONE_DIR)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            print("Clone complete.")
            return True
        except Exception as e:
            print(f"Error cloning: {e}")
            return False


def parse_maidata(maidata_path: Path) -> Optional[Dict]:
    """
    Parse a maidata.txt file into a dictionary of key-value pairs.

    The format uses &key=value sections where values can be multi-line
    (especially chart data in &inote_N= sections).
    """
    try:
        content = maidata_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        try:
            content = maidata_path.read_text(encoding="shift_jis")
        except Exception:
            return None

    result = {}
    # Split on & to get sections, but handle the first part before any &
    sections = content.split("&")

    for section in sections:
        if "=" not in section:
            continue
        key, _, value = section.partition("=")
        key = key.strip().lower()
        value = value.strip()
        # Remove trailing newlines but keep internal structure
        value = value.rstrip("\n").rstrip("\r")
        result[key] = value

    return result if result else None


def extract_chart_data(maidata: Dict, difficulty: str) -> Optional[str]:
    """
    Extract chart notation for a specific difficulty.

    Args:
        maidata: Parsed maidata dictionary
        difficulty: "master" (inote_5) or "remaster" (inote_6)

    Returns:
        Chart notation string, or None if not present
    """
    key_map = {"master": "inote_5", "remaster": "inote_6"}
    key = key_map.get(difficulty)
    if not key:
        return None

    chart = maidata.get(key)
    if not chart or not chart.strip():
        return None

    return chart.strip()


def build_simai_string(maidata: Dict, chart_data: str, difficulty: str) -> str:
    """
    Build a complete simai string that can be loaded by mai-notes.com player.

    Includes metadata headers and the chart notation for one difficulty.
    """
    lines = []

    title = maidata.get("title", "Unknown")
    lines.append(f"&title={title}")

    artist = maidata.get("artist", "")
    if artist:
        lines.append(f"&artist={artist}")

    bpm = maidata.get("wholebpm", "")
    if bpm:
        lines.append(f"&wholebpm={bpm}")

    first = maidata.get("first", "")
    if first:
        lines.append(f"&first={first}")

    des = maidata.get("des", "")
    if des:
        lines.append(f"&des={des}")

    # Add the difficulty level
    lv_key = "lv_5" if difficulty == "master" else "lv_6"
    lv = maidata.get(lv_key, "")
    if lv:
        lines.append(f"&{lv_key}={lv}")

    # Add the chart notation
    inote_key = "inote_5" if difficulty == "master" else "inote_6"
    lines.append(f"&{inote_key}={chart_data}")

    return "\n".join(lines)


def normalize_title(title: str) -> str:
    """
    Normalize a title for matching purposes.

    Strips [SD], [DX] suffixes, converts fullwidth to halfwidth,
    lowercases, and removes extra whitespace.
    """
    # Remove [SD], [DX], [宴] and similar suffixes
    title = re.sub(r"\s*\[(?:SD|DX|宴|協|蔵|狂|覚)\]\s*$", "", title)
    # Convert fullwidth characters to halfwidth
    title = unicodedata.normalize("NFKC", title)
    # Lowercase
    title = title.lower()
    # Remove extra whitespace
    title = " ".join(title.split())
    return title.strip()


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Replace characters invalid in Windows filenames
    invalid_chars = r'<>:"/\|?*'
    for ch in invalid_chars:
        name = name.replace(ch, "_")
    # Remove control characters
    name = "".join(c for c in name if ord(c) >= 32)
    return name.strip()


def build_song_indexes(songs: List[Dict]) -> Tuple[Dict, Dict]:
    """
    Build lookup indexes from output.json songs.

    Returns:
        (songs_by_id, songs_by_normalized_title)
    """
    songs_by_id = {}
    songs_by_normalized = {}

    for song in songs:
        sid = song.get("song_id", "")
        if sid:
            songs_by_id[sid] = song

        for field in ("title", "romaji", "english"):
            val = song.get(field, "")
            if val:
                norm = normalize_title(val)
                if norm not in songs_by_normalized:
                    songs_by_normalized[norm] = sid

    return songs_by_id, songs_by_normalized


def match_chart_to_song(
    chart_title: str,
    songs_by_id: Dict,
    songs_by_normalized: Dict,
) -> Optional[str]:
    """
    Match a chart title to a song_id from output.json.

    Uses multi-stage matching: exact -> normalized -> fuzzy.

    Returns:
        song_id if matched, None otherwise
    """
    # Stage 1: Exact match on song_id
    if chart_title in songs_by_id:
        return chart_title

    # Stage 2: Normalized match
    normalized = normalize_title(chart_title)
    if normalized in songs_by_normalized:
        return songs_by_normalized[normalized]

    # Stage 3: Fuzzy match with high threshold
    best_match = None
    best_ratio = 0.0
    for norm_title, song_id in songs_by_normalized.items():
        ratio = SequenceMatcher(None, normalized, norm_title).ratio()
        if ratio > best_ratio and ratio >= 0.85:
            best_ratio = ratio
            best_match = song_id

    return best_match


def process_all_charts():
    """Process all charts from the cloned repo and save to charts/ folder."""
    # Load songs from output.json
    if not OUTPUT_JSON.exists():
        print(f"Error: {OUTPUT_JSON} not found!")
        sys.exit(1)

    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        all_songs = json.load(f)

    songs_by_id, songs_by_normalized = build_song_indexes(all_songs)
    print(f"Loaded {len(songs_by_id)} unique songs from output.json")

    # Create charts directory
    CHARTS_DIR.mkdir(exist_ok=True)

    chart_index = {}
    unmatched = []
    stats = {"total_folders": 0, "matched": 0, "unmatched": 0, "charts_saved": 0}

    # Walk through all category folders
    for category in REPO_CATEGORIES:
        category_dir = CLONE_DIR / category
        if not category_dir.exists():
            print(f"  Warning: Category folder not found: {category}")
            continue

        print(f"\nProcessing category: {category}")

        # Each subdirectory is a song
        for song_dir in sorted(category_dir.iterdir()):
            if not song_dir.is_dir():
                continue

            maidata_path = song_dir / "maidata.txt"
            if not maidata_path.exists():
                continue

            stats["total_folders"] += 1

            # Parse the maidata.txt
            maidata = parse_maidata(maidata_path)
            if not maidata:
                continue

            chart_title = maidata.get("title", "")
            if not chart_title:
                continue

            # Match to output.json
            song_id = match_chart_to_song(chart_title, songs_by_id, songs_by_normalized)

            if not song_id:
                stats["unmatched"] += 1
                unmatched.append(
                    {
                        "chart_title": chart_title,
                        "folder": str(song_dir.relative_to(CLONE_DIR)),
                    }
                )
                continue

            stats["matched"] += 1

            # Check if we already have this song (avoid duplicates from SD/DX variants)
            # Keep both if chart data differs, prefer DX version
            existing = chart_index.get(song_id)

            # Process Master (inote_5)
            master_data = extract_chart_data(maidata, "master")
            if master_data:
                filename = sanitize_filename(f"{song_id}_master.txt")
                chart_path = CHARTS_DIR / filename

                # If we already have this song, skip SD if we already have DX
                should_write = True
                if existing and existing.get("master"):
                    # Prefer DX charts (they have [DX] in the title)
                    if "[DX]" in chart_title:
                        should_write = True
                    elif "[SD]" in chart_title:
                        should_write = False

                if should_write:
                    simai_str = build_simai_string(maidata, master_data, "master")
                    chart_path.write_text(simai_str, encoding="utf-8")
                    stats["charts_saved"] += 1

                    if song_id not in chart_index:
                        chart_index[song_id] = {
                            "song_id": song_id,
                            "master": filename,
                            "remaster": None,
                            "bpm": maidata.get("wholebpm", ""),
                        }
                    else:
                        chart_index[song_id]["master"] = filename

            # Process Re:Master (inote_6)
            remaster_data = extract_chart_data(maidata, "remaster")
            if remaster_data:
                filename = sanitize_filename(f"{song_id}_remaster.txt")
                chart_path = CHARTS_DIR / filename
                simai_str = build_simai_string(maidata, remaster_data, "remaster")
                chart_path.write_text(simai_str, encoding="utf-8")
                stats["charts_saved"] += 1

                if song_id not in chart_index:
                    chart_index[song_id] = {
                        "song_id": song_id,
                        "master": None,
                        "remaster": filename,
                        "bpm": maidata.get("wholebpm", ""),
                    }
                else:
                    chart_index[song_id]["remaster"] = filename

    # Save chart index
    with open(CHART_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(chart_index, f, indent=2, ensure_ascii=False)

    # Save unmatched charts
    if unmatched:
        with open(UNMATCHED_FILE, "w", encoding="utf-8") as f:
            json.dump(unmatched, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*50}")
    print(f"Chart Processing Summary")
    print(f"{'='*50}")
    print(f"Total song folders processed: {stats['total_folders']}")
    print(f"Matched to output.json:       {stats['matched']}")
    print(f"Unmatched:                    {stats['unmatched']}")
    print(f"Chart files saved:            {stats['charts_saved']}")
    print(f"Songs with charts:            {len(chart_index)}")
    print(f"\nChart index saved to: {CHART_INDEX_FILE}")
    if unmatched:
        print(f"Unmatched log saved to: {UNMATCHED_FILE}")


def main():
    """Main entry point."""
    print("MaiMai Chart Download & Processing Script")
    print("=" * 50)

    # Step 1: Clone or pull repository
    if not clone_or_pull_repo():
        print("Failed to clone/pull repository. Aborting.")
        sys.exit(1)

    # Step 2: Process all charts
    process_all_charts()

    print("\nDone!")


if __name__ == "__main__":
    main()
