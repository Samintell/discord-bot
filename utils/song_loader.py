"""
Utility functions for loading and filtering songs from output.json
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

# Get the project root directory (parent of utils/)
PROJECT_ROOT = Path(__file__).parent.parent

# Module-level cache for output.json to avoid repeated file reads
_all_songs_cache = None

def _get_all_songs() -> List[Dict]:
    """Load and cache all songs from output.json."""
    global _all_songs_cache
    if _all_songs_cache is None:
        output_json = PROJECT_ROOT / "output.json"
        if not output_json.exists():
            raise FileNotFoundError(f"output.json not found at {output_json}")
        with open(output_json, 'r', encoding='utf-8') as f:
            _all_songs_cache = json.load(f)
    return _all_songs_cache


def clear_song_cache() -> None:
    """Clear the cached song data, forcing a reload on next access."""
    global _all_songs_cache
    _all_songs_cache = None

def load_songs(
    difficulty: str = "master",
    category: Optional[str] = None,
    version: Optional[str] = None,
    region: Optional[str] = None,
    deduplicate: bool = True
) -> List[Dict]:
    """
    Load songs from output.json with filtering.

    Args:
        difficulty: Filter by difficulty (default: "master")
        category: Optional category filter (e.g., "POPS＆アニメ")
        version: Optional version filter (e.g., "FESTiVAL")
        region: Optional region filter (e.g., "jp", "intl", "usa")
        deduplicate: If True, deduplicate by song_id keeping highest level.
                     If False, return all matching entries (for chart mode).

    Returns:
        List of songs (deduplicated by song_id if deduplicate=True)
    """
    all_songs = _get_all_songs()

    if deduplicate:
        # Deduplicate by song_id, keeping the higher difficulty level
        filtered = {}
        for song in all_songs:
            song_difficulty = song.get('difficulty', '')
            if difficulty and song_difficulty not in ['master', 'remaster']:
                continue
            if category and song.get('category') != category:
                continue
            if version and song.get('version') != version:
                continue
            if region:
                song_regions = song.get('regions', [])
                if region not in song_regions:
                    continue

            song_id = song['song_id']
            if song_id not in filtered:
                filtered[song_id] = song
            else:
                current_level = filtered[song_id].get('level', 0)
                new_level = song.get('level', 0)
                if new_level > current_level:
                    filtered[song_id] = song

        return list(filtered.values())
    else:
        # Return all matching entries without deduplication
        filtered = []
        for song in all_songs:
            song_difficulty = song.get('difficulty', '')
            if difficulty and song_difficulty not in ['master', 'remaster']:
                continue
            if category and song.get('category') != category:
                continue
            if version and song.get('version') != version:
                continue
            if region:
                song_regions = song.get('regions', [])
                if region not in song_regions:
                    continue
            filtered.append(song)
        return filtered

def get_song_difficulties(song_id: str) -> Dict[str, float]:
    """
    Look up all master/remaster difficulty levels for a song_id.

    Returns:
        Dict like {'master': 13.5, 'remaster': 14.0} or {'master': 12.0}.
        Picks the highest level per difficulty across types (std/dx).
    """
    all_songs = _get_all_songs()

    difficulties = {}
    for song in all_songs:
        if song['song_id'] != song_id:
            continue
        diff = song.get('difficulty', '')
        level = song.get('level', 0)
        if diff in ('master', 'remaster'):
            if diff not in difficulties or level > difficulties[diff]:
                difficulties[diff] = level
    return difficulties


def get_song_chart_variants(song_id: str) -> Dict[str, Dict[str, float]]:
    """
    Look up master/remaster charts for a song_id grouped by chart type.

    Returns:
        Dict like {"std": {"master": 12.5, "remaster": 13.0}, "dx": {"master": 12.7}}
        Uses the highest level per (chart_type, difficulty).
    """
    all_songs = _get_all_songs()

    variants: Dict[str, Dict[str, float]] = {}
    for song in all_songs:
        if song.get("song_id") != song_id:
            continue
        diff = song.get("difficulty", "")
        if diff not in ("master", "remaster"):
            continue
        chart_type = (song.get("type") or "std").lower()
        level = song.get("level", 0)
        if chart_type not in variants:
            variants[chart_type] = {}
        current = variants[chart_type].get(diff)
        if current is None or level > current:
            variants[chart_type][diff] = level

    return variants

def get_song_image_path(song: Dict) -> Optional[Path]:
    """Get the path to a song's cover image."""
    image_name = song.get('image')
    if not image_name:
        return None

    image_path = PROJECT_ROOT / "images" / image_name
    return image_path if image_path.exists() else None

def get_song_audio_path(song: Dict) -> Optional[Path]:
    """Get the path to a song's audio file."""
    image_name = song.get('image')
    if not image_name:
        return None

    # Audio files use same name as images but with .mp3 extension
    audio_name = image_name.replace('.png', '.mp3')
    audio_path = PROJECT_ROOT / "audio" / audio_name
    return audio_path if audio_path.exists() else None

def get_song_chart_path(song: Dict, difficulty: str = "master") -> Optional[Path]:
    """Get the path to a song's processed simai chart file.

    Args:
        song: Song dictionary from output.json
        difficulty: "master" or "remaster" (default: "master")

    Returns:
        Path to the chart .txt file, or None if not available
    """
    song_id = song.get('song_id')
    if not song_id:
        return None

    # Chart files stored as: charts/{song_id}_{difficulty}.txt
    # Sanitize filename the same way as download_charts.py
    clean_id = song_id
    invalid_chars = '<>:"/\\|?*'
    for ch in invalid_chars:
        clean_id = clean_id.replace(ch, '_')

    chart_filename = f"{clean_id}_{difficulty}.txt"
    chart_path = PROJECT_ROOT / "charts" / chart_filename

    if chart_path.exists():
        return chart_path

    # Fallback: try remaster if master not found
    if difficulty == "master":
        remaster_filename = f"{clean_id}_remaster.txt"
        remaster_path = PROJECT_ROOT / "charts" / remaster_filename
        if remaster_path.exists():
            return remaster_path

    return None


def get_available_categories() -> List[str]:
    """Get list of all available categories."""
    all_songs = _get_all_songs()
    categories = set(song.get('category') for song in all_songs if song.get('category'))
    return sorted(categories)

def get_available_versions() -> List[str]:
    """Get list of all available versions."""
    all_songs = _get_all_songs()
    versions = set(song.get('version') for song in all_songs if song.get('version'))
    return sorted(versions)
