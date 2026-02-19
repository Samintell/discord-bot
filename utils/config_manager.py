"""
Manager for bot configuration files (translations, romaji overrides, aliases).
Provides load/save/add/remove operations with immediate persistence.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

CONFIG_DIR.mkdir(exist_ok=True)

TRANSLATIONS_FILE = CONFIG_DIR / "known_translations.json"
ROMAJI_FILE = CONFIG_DIR / "romaji_overrides.json"
ALIASES_FILE = CONFIG_DIR / "aliases.json"


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    """Save dict to JSON file with pretty formatting."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Known Translations (Japanese title -> English) ---

def load_translations() -> Dict[str, str]:
    return _load_json(TRANSLATIONS_FILE)


def add_translation(japanese_title: str, english: str) -> None:
    t = load_translations()
    t[japanese_title] = english
    _save_json(TRANSLATIONS_FILE, t)


def remove_translation(japanese_title: str) -> bool:
    t = load_translations()
    if japanese_title in t:
        del t[japanese_title]
        _save_json(TRANSLATIONS_FILE, t)
        return True
    return False


# --- Romaji Overrides (title -> romaji) ---

def load_romaji_overrides() -> Dict[str, str]:
    return _load_json(ROMAJI_FILE)


def add_romaji_override(title: str, romaji: str) -> None:
    r = load_romaji_overrides()
    r[title] = romaji
    _save_json(ROMAJI_FILE, r)


def remove_romaji_override(title: str) -> bool:
    r = load_romaji_overrides()
    if title in r:
        del r[title]
        _save_json(ROMAJI_FILE, r)
        return True
    return False


# --- Song Aliases (song_id -> list of alias strings) ---

def load_aliases() -> Dict[str, List[str]]:
    return _load_json(ALIASES_FILE)


def add_alias(song_id: str, alias: str) -> None:
    a = load_aliases()
    if song_id not in a:
        a[song_id] = []
    if alias not in a[song_id]:
        a[song_id].append(alias)
    _save_json(ALIASES_FILE, a)


def remove_alias(song_id: str, alias: str) -> bool:
    a = load_aliases()
    if song_id in a and alias in a[song_id]:
        a[song_id].remove(alias)
        if not a[song_id]:
            del a[song_id]
        _save_json(ALIASES_FILE, a)
        return True
    return False


def get_aliases_for_song(song_id: str) -> List[str]:
    return load_aliases().get(song_id, [])
