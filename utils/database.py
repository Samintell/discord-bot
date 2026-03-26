"""
SQLite database manager for maimai NET user tokens and cached scores.
Uses aiosqlite for async access and Fernet for token encryption.
"""

import os
import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional, Set
from cryptography.fernet import Fernet

from utils.constants import RANK_THRESHOLDS, FC_HIERARCHY

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "maimai_data.db"

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Get or create the Fernet encryption instance."""
    global _fernet
    if _fernet is None:
        secret = os.getenv("TOKEN_SECRET")
        if not secret:
            raise RuntimeError("TOKEN_SECRET environment variable is not set")
        _fernet = Fernet(secret.encode())
    return _fernet


async def init_db() -> None:
    """Create database tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                discord_user_id TEXT NOT NULL,
                encrypted_token TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_scores (
                discord_user_id TEXT NOT NULL,
                song_id TEXT NOT NULL,
                song_name TEXT NOT NULL,
                chart_type TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                level TEXT NOT NULL,
                achievement INTEGER NOT NULL,
                dx_score INTEGER NOT NULL,
                fc TEXT NOT NULL DEFAULT 'none',
                fs TEXT NOT NULL DEFAULT 'none',
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id, song_id, chart_type, difficulty)
            )
        """)
        await db.commit()


# --- Token operations ---

async def save_token(discord_user_id: str, token: str) -> None:
    """Encrypt and store a maimai NET token for a user."""
    f = _get_fernet()
    encrypted = f.encrypt(token.encode()).decode()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_tokens (discord_user_id, encrypted_token, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                encrypted_token = excluded.encrypted_token,
                updated_at = CURRENT_TIMESTAMP
        """, (discord_user_id, encrypted))
        await db.commit()


async def get_token(discord_user_id: str) -> Optional[str]:
    """Retrieve and decrypt a user's maimai NET token."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT encrypted_token FROM user_tokens WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        f = _get_fernet()
        return f.decrypt(row[0].encode()).decode()


async def delete_token(discord_user_id: str) -> bool:
    """Remove a user's stored token. Returns True if a token was deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_tokens WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# --- Score operations ---

async def save_scores(discord_user_id: str, scores: List[Dict]) -> int:
    """Store matched user scores in the database.

    Each score dict should have: song_id, song_name, chart_type, difficulty,
    level, achievement, dx_score, fc, fs.

    Returns the number of scores saved.
    """
    if not scores:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        # Clear old scores for this user before inserting fresh data
        await db.execute(
            "DELETE FROM user_scores WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        await db.executemany("""
            INSERT INTO user_scores
                (discord_user_id, song_id, song_name, chart_type, difficulty,
                 level, achievement, dx_score, fc, fs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                discord_user_id,
                s["song_id"], s["song_name"], s["chart_type"], s["difficulty"],
                s["level"], s["achievement"], s["dx_score"], s["fc"], s["fs"]
            )
            for s in scores
        ])
        await db.commit()
        return len(scores)


async def delete_scores(discord_user_id: str) -> None:
    """Remove all cached scores for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_scores WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        await db.commit()


async def get_filtered_song_ids(
    discord_user_id: str,
    difficulties: List[str],
    min_rank: Optional[str] = None,
    min_combo: Optional[str] = None,
) -> Set[str]:
    """Get song_ids where user's scores meet the given thresholds.

    Args:
        discord_user_id: Discord user ID
        difficulties: List of difficulty names to check (e.g., ["master", "expert"])
        min_rank: Minimum achievement rank (e.g., "S", "SS+")
        min_combo: Minimum FC status (e.g., "FC", "AP")

    Returns:
        Set of song_ids that meet ALL specified criteria on ANY of the given difficulties.
    """
    conditions = ["discord_user_id = ?"]
    params: list = [discord_user_id]

    # Difficulty filter
    placeholders = ",".join("?" for _ in difficulties)
    conditions.append(f"difficulty IN ({placeholders})")
    params.extend(difficulties)

    # Achievement rank filter
    if min_rank and min_rank in RANK_THRESHOLDS:
        conditions.append("achievement >= ?")
        params.append(RANK_THRESHOLDS[min_rank])

    # FC/combo filter
    if min_combo and min_combo.lower() in FC_HIERARCHY:
        min_fc_index = FC_HIERARCHY.index(min_combo.lower())
        valid_fc = FC_HIERARCHY[min_fc_index:]
        fc_placeholders = ",".join("?" for _ in valid_fc)
        conditions.append(f"fc IN ({fc_placeholders})")
        params.extend(valid_fc)

    where_clause = " AND ".join(conditions)
    query = f"SELECT DISTINCT song_id FROM user_scores WHERE {where_clause}"

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


async def has_scores(discord_user_id: str) -> bool:
    """Check if a user has any cached scores."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM user_scores WHERE discord_user_id = ? LIMIT 1",
            (discord_user_id,)
        )
        return await cursor.fetchone() is not None


async def get_score_summary(discord_user_id: str) -> Optional[Dict]:
    """Get a summary of a user's cached scores for display.

    Returns dict with total_scores, difficulty breakdown, and rank breakdown,
    or None if no scores exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Total count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM user_scores WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0
        if total == 0:
            return None

        # Count distinct songs
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT song_id) FROM user_scores WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        unique_songs = row[0] if row else 0

        # Breakdown by difficulty
        cursor = await db.execute(
            "SELECT difficulty, COUNT(*) FROM user_scores WHERE discord_user_id = ? GROUP BY difficulty ORDER BY difficulty",
            (discord_user_id,)
        )
        difficulty_counts = {row[0]: row[1] for row in await cursor.fetchall()}

        # Rank distribution for expert/master/remaster
        rank_counts = {}
        for rank_name, threshold in sorted(RANK_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT song_id) FROM user_scores WHERE discord_user_id = ? AND difficulty IN ('expert', 'master', 'remaster') AND achievement >= ?",
                (discord_user_id, threshold)
            )
            row = await cursor.fetchone()
            rank_counts[rank_name] = row[0] if row else 0

        return {
            "total_scores": total,
            "unique_songs": unique_songs,
            "by_difficulty": difficulty_counts,
            "rank_counts": rank_counts,
        }
