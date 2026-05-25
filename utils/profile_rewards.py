"""
Reward calculation helpers for profile currency.
"""

import math
from typing import Dict

from utils.constants import DEFAULT_SNIPPET_LENGTH
MIN_POOL_SIZE = 10
MAX_POOL_MULTIPLIER = 5.0

MODE_MULTIPLIERS = {
    "image": 2.0,
    "audio": 5.0,
    "chart": 10.0,
}

ANSWER_TYPE_MULTIPLIERS = {
    "difficulty": 0.2,
    "artist": 0.8,
    "title": 1.0,
}

GLOBAL_MULTIPLIER = 2.0

IMAGE_DIFFICULTY_MULTIPLIERS = {
    "easy": 1.0,
    "medium": 2.0,
    "hard": 3.0,
}


def calculate_length_multiplier(mode: str, snippet_length: float, image_difficulty: str) -> float:
    if mode in ("audio", "chart"):
        if snippet_length <= 0:
            return 1.0
        return float(DEFAULT_SNIPPET_LENGTH) / float(snippet_length)
    if mode == "image":
        return IMAGE_DIFFICULTY_MULTIPLIERS.get(image_difficulty, 1.0)
    return 1.0


def calculate_pool_multiplier(eligible_song_count: int, total_song_count: int) -> float:
    if eligible_song_count <= MIN_POOL_SIZE or total_song_count <= MIN_POOL_SIZE:
        return 1.0

    total_clamped = max(total_song_count, MIN_POOL_SIZE)
    eligible_clamped = min(max(eligible_song_count, MIN_POOL_SIZE), total_clamped)

    if total_clamped == MIN_POOL_SIZE:
        return 1.0

    ratio = math.log(eligible_clamped / MIN_POOL_SIZE) / math.log(total_clamped / MIN_POOL_SIZE)
    multiplier = 1.0 + (MAX_POOL_MULTIPLIER - 1.0) * ratio
    return min(MAX_POOL_MULTIPLIER, max(1.0, multiplier))


def calculate_reward_breakdown(
    mode: str,
    answer_type: str,
    snippet_length: float,
    image_difficulty: str,
    eligible_song_count: int,
    total_song_count: int,
) -> Dict[str, float]:
    mode_multiplier = MODE_MULTIPLIERS.get(mode, 1.0)
    answer_multiplier = ANSWER_TYPE_MULTIPLIERS.get(answer_type, 1.0)
    length_multiplier = calculate_length_multiplier(mode, snippet_length, image_difficulty)
    pool_multiplier = calculate_pool_multiplier(eligible_song_count, total_song_count)
    total_multiplier = (
        mode_multiplier
        * answer_multiplier
        * length_multiplier
        * pool_multiplier
        * GLOBAL_MULTIPLIER
    )

    return {
        "mode_multiplier": mode_multiplier,
        "answer_multiplier": answer_multiplier,
        "length_multiplier": length_multiplier,
        "pool_multiplier": pool_multiplier,
        "global_multiplier": GLOBAL_MULTIPLIER,
        "total_multiplier": total_multiplier,
    }


def calculate_coin_reward(correct_guesses: int, total_multiplier: float) -> int:
    if correct_guesses <= 0:
        return 0
    return int(math.ceil(correct_guesses * total_multiplier))
