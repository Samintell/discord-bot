"""
Profile shop catalog and helpers.
"""

import json
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent
SHOP_FILE = PROJECT_ROOT / "config" / "profile_shop.json"

DEFAULT_SHOP_ITEMS: Dict[str, dict] = {
    "banner_basic": {
        "type": "banner",
        "name": "Basic Banner",
        "price": 2000,
        "image_url": "https://placehold.co/600x200/png?text=Basic+Banner",
        "description": "Simple and clean.",
    },
    "banner_sunset": {
        "type": "banner",
        "name": "Sunset Banner",
        "price": 2000,
        "image_url": "https://placehold.co/600x200/png?text=Sunset+Banner",
        "description": "Warm gradient vibes.",
    },
    "banner_neon": {
        "type": "banner",
        "name": "Neon Grid",
        "price": 2000,
        "image_url": "https://placehold.co/600x200/png?text=Neon+Grid",
        "description": "Electric and bold.",
    },
    "partner_mascot": {
        "type": "partner",
        "name": "Mascot Buddy",
        "price": 5000,
        "image_url": "https://placehold.co/256x256/png?text=Mascot",
        "description": "Your cheerful sidekick.",
    },
    "partner_dj": {
        "type": "partner",
        "name": "DJ Pal",
        "price": 5000,
        "image_url": "https://placehold.co/256x256/png?text=DJ+Pal",
        "description": "Always on the beat.",
    },
}


def load_shop_items() -> Dict[str, dict]:
    if SHOP_FILE.exists():
        try:
            with open(SHOP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_SHOP_ITEMS


def get_shop_item(item_id: str) -> Optional[dict]:
    return load_shop_items().get(item_id)
