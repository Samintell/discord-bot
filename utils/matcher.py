"""
Answer matching logic with fuzzy string matching support.
Handles both Japanese and romaji answers with partial matching.
"""

from difflib import SequenceMatcher
import re
from typing import Dict

def normalize_string(text: str) -> str:
    """
    Normalize string for matching: lowercase, remove punctuation, strip whitespace.
    
    Args:
        text: String to normalize
    
    Returns:
        Normalized string
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove common punctuation (but keep Japanese characters)
    text = re.sub(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?`~]', ' ', text)
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    return text

def fuzzy_match(guess: str, target: str, threshold: float = 0.8) -> bool:
    """
    Check if guess matches target using fuzzy string matching.
    
    Args:
        guess: User's guess
        target: Correct answer
        threshold: Similarity threshold (0-1, default 0.8)
    
    Returns:
        True if match is found
    """
    guess_norm = normalize_string(guess)
    target_norm = normalize_string(target)
    
    if not guess_norm or not target_norm:
        return False
    
    # Require minimum length (at least 3 characters or 40% of target length)
    min_length = max(3, int(len(target_norm) * 0.4))
    if len(guess_norm) < min_length:
        return False
    
    # Check if guess is a substring of target (partial match)
    if guess_norm in target_norm:
        return True
    
    # Check if target is a substring of guess
    if target_norm in guess_norm:
        return True
    
    # Use fuzzy matching for similarity
    similarity = SequenceMatcher(None, guess_norm, target_norm).ratio()
    return similarity >= threshold

def check_difficulty(guess: str, song: Dict, exact_only: bool = False) -> bool:
    """
    Check if a difficulty guess matches the song's difficulty level.
    
    Args:
        guess: User's guess (should be a number)
        song: Song dictionary from output.json
        exact_only: If True, require exact match. If False, allow ±0.5 tolerance
    
    Returns:
        True if the guess is correct
    """
    try:
        # Extract numeric value from guess
        guess_clean = guess.strip().replace(',', '.').replace('+', '')
        guess_num = float(guess_clean)
        
        # Get song difficulty level
        target_level = song.get('level', 0)
        
        if exact_only:
            # Require exact match
            return abs(guess_num - target_level) < 0.01
        else:
            # Allow small tolerance (±0.5)
            return abs(guess_num - target_level) <= 0.5
    except (ValueError, TypeError):
        return False

def check_answer(guess: str, song: Dict, answer_type: str = "title", threshold: float = 0.8) -> bool:
    """
    Check if a guess matches the correct answer.
    
    Args:
        guess: User's guess
        song: Song dictionary from output.json
        answer_type: "title", "artist", or "difficulty"
        threshold: Fuzzy matching threshold (0-1)
    
    Returns:
        True if the guess is correct
    """
    if answer_type == "title":
        # Check against Japanese title, romaji, and English translation
        japanese_title = song.get('title', '')
        romaji_title = song.get('romaji', '')
        english_title = song.get('english', '')
        
        if fuzzy_match(guess, japanese_title, threshold):
            return True
        if romaji_title and fuzzy_match(guess, romaji_title, threshold):
            return True
        if english_title and fuzzy_match(guess, english_title, threshold):
            return True
    
    elif answer_type == "artist":
        # Check against artist name
        artist = song.get('artist', '')
        if fuzzy_match(guess, artist, threshold):
            return True
    
    elif answer_type == "difficulty":
        # Check difficulty level (exact match required)
        return check_difficulty(guess, song, exact_only=True)
    
    return False
