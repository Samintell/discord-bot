"""
Utility functions for loading and filtering songs from output.json
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

def load_songs(
    difficulty: str = "master",
    category: Optional[str] = None,
    version: Optional[str] = None
) -> List[Dict]:
    """
    Load songs from output.json with filtering.
    
    Args:
        difficulty: Filter by difficulty (default: "master")
        category: Optional category filter (e.g., "POPS＆アニメ")
        version: Optional version filter (e.g., "FESTiVAL")
    
    Returns:
        List of unique songs (deduplicated by song_id)
    """
    output_json = Path("output.json")
    
    if not output_json.exists():
        raise FileNotFoundError("output.json not found")
    
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
    
    image_path = Path("images") / image_name
    return image_path if image_path.exists() else None

def get_song_audio_path(song: Dict) -> Optional[Path]:
    """Get the path to a song's audio file."""
    image_name = song.get('image')
    if not image_name:
        return None
    
    # Audio files use same name as images but with .mp3 extension
    audio_name = image_name.replace('.png', '.mp3')
    audio_path = Path("audio") / audio_name
    return audio_path if audio_path.exists() else None

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
