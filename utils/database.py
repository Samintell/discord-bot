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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                discord_user_id TEXT NOT NULL,
                total_correct INTEGER NOT NULL DEFAULT 0,
                total_games INTEGER NOT NULL DEFAULT 0,
                coins_balance INTEGER NOT NULL DEFAULT 0,
                coins_lifetime INTEGER NOT NULL DEFAULT 0,
                banner_id TEXT,
                partner_id TEXT,
                name_language TEXT DEFAULT 'japanese',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_inventory (
                discord_user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                purchased_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id, item_id)
            )
        """)
        
        # Migration: Add name_language if it doesn't exist
        try:
            await db.execute("ALTER TABLE user_profiles ADD COLUMN name_language TEXT DEFAULT 'japanese'")
        except aiosqlite.OperationalError:
            pass # Column already exists
            
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


async def get_filtered_chart_keys(
    discord_user_id: str,
    difficulties: List[str],
    min_rank: Optional[str] = None,
    min_combo: Optional[str] = None,
) -> Set[tuple[str, str, str]]:
    """Get (song_id, chart_type, difficulty) where scores meet thresholds.

    Returns a set of tuples matching the requested difficulties. This is
    useful for chart mode so std/dx and master/remaster are respected.
    """
    conditions = ["discord_user_id = ?"]
    params: list = [discord_user_id]

    placeholders = ",".join("?" for _ in difficulties)
    conditions.append(f"difficulty IN ({placeholders})")
    params.extend(difficulties)

    if min_rank and min_rank in RANK_THRESHOLDS:
        conditions.append("achievement >= ?")
        params.append(RANK_THRESHOLDS[min_rank])

    if min_combo and min_combo.lower() in FC_HIERARCHY:
        min_fc_index = FC_HIERARCHY.index(min_combo.lower())
        valid_fc = FC_HIERARCHY[min_fc_index:]
        fc_placeholders = ",".join("?" for _ in valid_fc)
        conditions.append(f"fc IN ({fc_placeholders})")
        params.extend(valid_fc)

    where_clause = " AND ".join(conditions)
    query = (
        "SELECT DISTINCT song_id, chart_type, difficulty "
        "FROM user_scores WHERE "
        f"{where_clause}"
    )

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return {
            (row[0], str(row[1]).lower(), str(row[2]).lower())
            for row in rows
        }


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


async def _ensure_profile(db: aiosqlite.Connection, discord_user_id: str) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO user_profiles (discord_user_id) VALUES (?)",
        (discord_user_id,)
    )


async def get_profile(discord_user_id: str) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        cursor = await db.execute(
            """
            SELECT total_correct, total_games, coins_balance, coins_lifetime, banner_id, partner_id, name_language
            FROM user_profiles WHERE discord_user_id = ?
            """,
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        await db.commit()

        if not row:
            return {
                "total_correct": 0,
                "total_games": 0,
                "coins_balance": 0,
                "coins_lifetime": 0,
                "banner_id": None,
                "partner_id": None,
                "name_language": "japanese",
            }

        return {
            "total_correct": row[0],
            "total_games": row[1],
            "coins_balance": row[2],
            "coins_lifetime": row[3],
            "banner_id": row[4],
            "partner_id": row[5],
            "name_language": row[6] if len(row) > 6 else "japanese",
        }


async def record_quiz_rewards(
    discord_user_id: str,
    correct_delta: int,
    games_delta: int,
    coins_delta: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        await db.execute(
            """
            UPDATE user_profiles
            SET total_correct = total_correct + ?,
                total_games = total_games + ?,
                coins_balance = coins_balance + ?,
                coins_lifetime = coins_lifetime + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (correct_delta, games_delta, coins_delta, coins_delta, discord_user_id),
        )
        await db.commit()


async def spend_coins(discord_user_id: str, amount: int) -> bool:
    if amount <= 0:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        cursor = await db.execute(
            "SELECT coins_balance FROM user_profiles WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        balance = row[0] if row else 0
        if balance < amount:
            return False

        await db.execute(
            """
            UPDATE user_profiles
            SET coins_balance = coins_balance - ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (amount, discord_user_id),
        )
        await db.commit()
        return True


async def add_inventory_item(discord_user_id: str, item_id: str, item_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        await db.execute(
            """
            INSERT OR IGNORE INTO user_inventory (discord_user_id, item_id, item_type)
            VALUES (?, ?, ?)
            """,
            (discord_user_id, item_id, item_type),
        )
        await db.commit()


async def has_inventory_item(discord_user_id: str, item_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT 1 FROM user_inventory
            WHERE discord_user_id = ? AND item_id = ?
            LIMIT 1
            """,
            (discord_user_id, item_id),
        )
        return await cursor.fetchone() is not None


async def list_inventory_items(discord_user_id: str, item_type: Optional[str] = None) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        if item_type:
            cursor = await db.execute(
                """
                SELECT item_id FROM user_inventory
                WHERE discord_user_id = ? AND item_type = ?
                ORDER BY item_id
                """,
                (discord_user_id, item_type),
            )
        else:
            cursor = await db.execute(
                """
                SELECT item_id FROM user_inventory
                WHERE discord_user_id = ?
                ORDER BY item_id
                """,
                (discord_user_id,),
            )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def set_profile_banner(discord_user_id: str, banner_id: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        await db.execute(
            """
            UPDATE user_profiles
            SET banner_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (banner_id, discord_user_id),
        )
        await db.commit()


async def set_profile_partner(discord_user_id: str, partner_id: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        await db.execute(
            """
            UPDATE user_profiles
            SET partner_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (partner_id, discord_user_id),
        )
        await db.commit()


async def set_profile_coins_balance(discord_user_id: str, balance: int) -> None:
    if balance < 0:
        balance = 0
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        cursor = await db.execute(
            "SELECT coins_lifetime FROM user_profiles WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        row = await cursor.fetchone()
        lifetime = row[0] if row else 0
        new_lifetime = max(lifetime, balance)

        await db.execute(
            """
            UPDATE user_profiles
            SET coins_balance = ?,
                coins_lifetime = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (balance, new_lifetime, discord_user_id),
        )
        await db.commit()

async def set_user_language(discord_user_id: str, language: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_profile(db, discord_user_id)
        await db.execute(
            """
            UPDATE user_profiles
            SET name_language = ?, updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (language, discord_user_id),
        )
        await db.commit()
