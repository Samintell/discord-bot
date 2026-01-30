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
    More lenient for longer targets.
    
    Args:
        guess: User's guess
        target: Correct answer
        threshold: Base similarity threshold (0-1, default 0.8)
    
    Returns:
        True if match is found
    """
    guess_norm = normalize_string(guess)
    target_norm = normalize_string(target)
    
    if not guess_norm or not target_norm:
        return False
    
    # Calculate minimum required length based on target length
    # Short titles (< 10 chars): require 40% of length
    # Medium titles (10-20 chars): require 35% of length  
    # Long titles (20-40 chars): require 30% of length
    # Very long titles (40+ chars): require 25% of length, min 10 chars
    target_len = len(target_norm)
    if target_len < 10:
        min_length = max(3, int(target_len * 0.4))
    elif target_len < 20:
        min_length = max(4, int(target_len * 0.35))
    elif target_len < 40:
        min_length = max(6, int(target_len * 0.3))
    else:
        min_length = max(10, int(target_len * 0.25))
    
    if len(guess_norm) < min_length:
        return False
    
    # Check if guess is a substring of target (partial match)
    if guess_norm in target_norm:
        return True
    
    # Check if target is a substring of guess
    if target_norm in guess_norm:
        return True
    
    # For long targets, also check if guess matches the START of the target
    # This allows typing just the beginning of a long title
    if target_len > 15 and len(guess_norm) >= 6:
        if target_norm.startswith(guess_norm):
            return True
        # Also check first N characters with some leniency
        check_len = min(len(guess_norm), len(target_norm))
        start_similarity = SequenceMatcher(None, guess_norm[:check_len], target_norm[:check_len]).ratio()
        if start_similarity >= 0.85:
            return True
    
    # Adjust threshold based on target length (more lenient for longer targets)
    if target_len > 30:
        threshold = min(threshold, 0.65)
    elif target_len > 20:
        threshold = min(threshold, 0.7)
    elif target_len > 15:
        threshold = min(threshold, 0.75)
    
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
