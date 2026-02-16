"""
Utility functions for loading and filtering songs from output.json
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

# Get the project root directory (parent of utils/)
PROJECT_ROOT = Path(__file__).parent.parent

def load_songs(
    difficulty: str = "master",
    category: Optional[str] = None,
    version: Optional[str] = None,
    region: Optional[str] = None
) -> List[Dict]:
    """
    Load songs from output.json with filtering.
    
    Args:
        difficulty: Filter by difficulty (default: "master")
        category: Optional category filter (e.g., "POPS＆アニメ")
        version: Optional version filter (e.g., "FESTiVAL")
        region: Optional region filter (e.g., "jp", "intl", "usa")
    
    Returns:
        List of unique songs (deduplicated by song_id)
    """
    output_json = PROJECT_ROOT / "output.json"
    
    if not output_json.exists():
        raise FileNotFoundError(f"output.json not found at {output_json}")
    
    with open(output_json, 'r', encoding='utf-8') as f:
        all_songs = json.load(f)
    
    # Filter songs
    filtered = {}
    for song in all_songs:
        # Apply filters (accept both master and remaster)
        song_difficulty = song.get('difficulty', '')
        if difficulty and song_difficulty not in ['master', 'remaster']:
            continue
        if category and song.get('category') != category:
            continue
        if version and song.get('version') != version:
            continue
        # Apply region filter if specified
        if region:
            song_regions = song.get('regions', [])
            if region not in song_regions:
                continue
        
        # Deduplicate by song_id, keeping the higher difficulty level
        song_id = song['song_id']
        if song_id not in filtered:
            filtered[song_id] = song
        else:
            # If this song has a higher level, replace it
            current_level = filtered[song_id].get('level', 0)
            new_level = song.get('level', 0)
            if new_level > current_level:
                filtered[song_id] = song
    
    return list(filtered.values())

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
    output_json = Path("output.json")
    
    with open(output_json, 'r', encoding='utf-8') as f:
        all_songs = json.load(f)
    
    categories = set(song.get('category') for song in all_songs if song.get('category'))
    return sorted(categories)

def get_available_versions() -> List[str]:
    """Get list of all available versions."""
    output_json = Path("output.json")
    
    with open(output_json, 'r', encoding='utf-8') as f:
        all_songs = json.load(f)
    
    versions = set(song.get('version') for song in all_songs if song.get('version'))
    return sorted(versions)
