import math
import asyncio
from typing import Dict, List, Tuple
from utils.database import get_token, save_scores
from utils.maimai_scraper import fetch_all_scores, match_scores_to_songs
from utils.song_loader import _get_all_songs
from utils.config_manager import get_b50_active_versions
import aiosqlite
from utils.database import DB_PATH

# Chronological order of major versions to determine "New" songs
VERSION_ORDER = [
    "maimai", "maimai PLUS", "GreeN", "GreeN PLUS", "ORANGE", "ORANGE PLUS",
    "PiNK", "PiNK PLUS", "MURASAKi", "MURASAKi PLUS", "MiLK", "MiLK PLUS",
    "FiNALE", "maimaiでらっくす", "maimaiでらっくす PLUS", "Splash", "Splash PLUS",
    "UNiVERSE", "UNiVERSE PLUS", "FESTiVAL", "FESTiVAL PLUS", "BUDDiES",
    "BUDDiES PLUS", "PRiSM", "PRiSM PLUS"
]

def get_rating_coefficient(achievement: float) -> float:
    if achievement >= 100.5000: return 22.4
    if achievement >= 100.0000: return 21.6
    if achievement >= 99.5000: return 21.1
    if achievement >= 99.0000: return 20.8
    if achievement >= 98.0000: return 20.3
    if achievement >= 97.0000: return 20.0
    if achievement >= 94.0000: return 16.8
    if achievement >= 90.0000: return 15.2
    if achievement >= 80.0000: return 13.6
    if achievement >= 75.0000: return 12.0
    if achievement >= 70.0000: return 11.2
    if achievement >= 60.0000: return 9.6
    if achievement >= 50.0000: return 8.0
    if achievement >= 40.0000: return 6.4
    if achievement >= 30.0000: return 4.8
    if achievement >= 20.0000: return 3.2
    if achievement >= 10.0000: return 1.6
    return 0.0

def calculate_rating(level: float, achievement: float) -> int:
    """Calculates maimai DX rating for a specific score."""
    coef = get_rating_coefficient(achievement)
    # The max achievement applied for the multiplier calculation is 100.5%
    capped_achieve = min(100.5, achievement)
    return math.floor(level * coef * (capped_achieve / 100.0))

class B50Calculator:
    def __init__(self, discord_user_id: str):
        self.discord_user_id = discord_user_id
        self.used_cache = False
        self.error_message = None

    async def get_b50(self) -> Tuple[List[Dict], List[Dict], int]:
        """
        Fetches scores, calculates ratings, and returns:
        (top_15_new, top_35_old, total_rating)
        """
        token = None
        try:
            token = await get_token(self.discord_user_id)
        except RuntimeError:
            pass
        
        scores = []
        if token:
            try:
                # We can't use progress callbacks easily here as we just want silent fetching
                raw_scores = await fetch_all_scores(token)
                if raw_scores:
                    matched_scores, _ = match_scores_to_songs(raw_scores)
                    await save_scores(self.discord_user_id, matched_scores)
                    scores = matched_scores
                else:
                    self.used_cache = True
                    self.error_message = "No scores found on maimai NET, using cached data."
            except Exception as e:
                self.used_cache = True
                self.error_message = f"Failed to fetch from maimai NET ({e}), using cached data."
        else:
            self.used_cache = True
        
        if not scores:
            # Fallback to local DB
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT song_id, song_name, chart_type, difficulty,
                           level, achievement, dx_score, fc, fs
                    FROM user_scores
                    WHERE discord_user_id = ?
                    """,
                    (self.discord_user_id,)
                )
                rows = await cursor.fetchall()
                scores = [dict(row) for row in rows]
                
        if not scores:
            return [], [], 0

        # Load all songs to get versions and check which is the latest active version
        all_songs = _get_all_songs()
        song_dict = {}
        active_versions = set()
        
        for song in all_songs:
            # Create a unique key for each chart
            key = (song.get('song_id'), song.get('type', 'std').lower(), song.get('difficulty', '').lower())
            song_dict[key] = song
            version = song.get('version')
            if version:
                active_versions.add(version)
                
        # Determine the newest version available in output.json (for dynamic fallback)
        newest_version_idx = -1
        for v in active_versions:
            if v in VERSION_ORDER:
                idx = VERSION_ORDER.index(v)
                if idx > newest_version_idx:
                    newest_version_idx = idx
        
        # Load from config, or fallback to dynamic
        configured_versions = get_b50_active_versions()
        latest_versions = set(configured_versions)
        
        if not latest_versions and newest_version_idx != -1:
            latest_versions.add(VERSION_ORDER[newest_version_idx])
            base_version = VERSION_ORDER[newest_version_idx].replace(" PLUS", "")
            latest_versions.add(base_version)
            latest_versions.add(base_version + " PLUS")

        new_scores = []
        old_scores = []

        # Calculate rating for each score and separate into New/Old
        for score in scores:
            # Lookup full song data first to get the true internal level
            key = (score['song_id'], score['chart_type'].lower(), score['difficulty'].lower())
            full_song = song_dict.get(key)
            
            level = 0.0
            if full_song:
                try:
                    level = float(full_song.get('level', 0.0))
                except (ValueError, TypeError):
                    pass
            else:
                # Fallback to the score's level if full song data is missing
                try:
                    # rough fallback for 14+ -> 14.5
                    level_str = str(score.get('level', '0')).replace('+', '.5')
                    level = float(level_str)
                except ValueError:
                    pass
                
            achievement_pct = score.get('achievement', 0) / 10000.0
            rating = calculate_rating(level, achievement_pct)
            
            score_data = {
                'song_id': score['song_id'],
                'song_name': score['song_name'],
                'chart_type': score['chart_type'].lower(),
                'difficulty': score['difficulty'].lower(),
                'level': level,
                'achievement': achievement_pct,
                'rating': rating,
                'fc': score.get('fc', ''),
                'fs': score.get('fs', '')
            }
            
            if full_song:
                score_data['image'] = full_song.get('image')
                score_data['romaji'] = full_song.get('romaji')
                score_data['english'] = full_song.get('english')
                score_version = full_song.get('version')
            else:
                score_data['image'] = None
                score_version = "Unknown"
                
            if score_version in latest_versions:
                new_scores.append(score_data)
            else:
                old_scores.append(score_data)

        # Sort descending by rating
        new_scores.sort(key=lambda x: x['rating'], reverse=True)
        old_scores.sort(key=lambda x: x['rating'], reverse=True)

        top_15_new = new_scores[:15]
        top_35_old = old_scores[:35]
        
        total_rating = sum(s['rating'] for s in top_15_new) + sum(s['rating'] for s in top_35_old)
        
        return top_15_new, top_35_old, total_rating
