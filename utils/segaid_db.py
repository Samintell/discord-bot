"""
Separate SQLite database for SEGA ID login credentials and auth tokens.

All login information is kept in its own DB file (segaid_accounts.db) so it
never mixes with game data in maimai_data.db:
- `segaid_accounts`  - SEGA ID username + encrypted password
- `user_tokens`      - encrypted clal session cookies (formerly in maimai_data.db)

Passwords and tokens are encrypted with the same TOKEN_SECRET used before.
On init, any existing user_tokens in maimai_data.db are migrated here.
"""

import aiosqlite
from pathlib import Path
from typing import Dict, Optional

from utils.database import PROJECT_ROOT, DB_PATH, _get_fernet

SEGAID_DB_PATH = PROJECT_ROOT / "segaid_accounts.db"


async def init_segaid_db() -> None:
    """Create tables and migrate any existing auth tokens from the old database."""
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS segaid_accounts (
                discord_user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                encrypted_password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                discord_user_id TEXT NOT NULL,
                encrypted_token TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id)
            )
        """)
        await db.commit()

    await _migrate_old_tokens()


async def _migrate_old_tokens() -> None:
    """Copy user_tokens from maimai_data.db into the auth db, then drop the old table."""
    try:
        async with aiosqlite.connect(DB_PATH) as old_db:
            cursor = await old_db.execute(
                "SELECT discord_user_id, encrypted_token, created_at, updated_at FROM user_tokens"
            )
            rows = await cursor.fetchall()
    except aiosqlite.OperationalError:
        rows = []  # Old table doesn't exist (fresh install)

    if rows:
        async with aiosqlite.connect(SEGAID_DB_PATH) as db:
            await db.executemany("""
                INSERT OR IGNORE INTO user_tokens (discord_user_id, encrypted_token, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, rows)
            await db.commit()

        # Tokens now live in the auth db - remove the old table
        try:
            async with aiosqlite.connect(DB_PATH) as old_db:
                await old_db.execute("DROP TABLE IF EXISTS user_tokens")
                await old_db.commit()
        except aiosqlite.OperationalError:
            pass


# --- Auth token operations (clal session cookies) ---

async def save_token(discord_user_id: str, token: str) -> None:
    """Encrypt and store a maimai NET clal token for a user."""
    f = _get_fernet()
    encrypted = f.encrypt(token.encode()).decode()
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_tokens (discord_user_id, encrypted_token, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                encrypted_token = excluded.encrypted_token,
                updated_at = CURRENT_TIMESTAMP
        """, (discord_user_id, encrypted))
        await db.commit()


async def get_token(discord_user_id: str) -> Optional[str]:
    """Retrieve and decrypt a user's maimai NET clal token."""
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
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
    """Remove a user's stored clal token. Returns True if a token was deleted."""
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_tokens WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# --- SEGA ID credential operations ---

async def save_segaid_account(discord_user_id: str, username: str, password: str) -> None:
    """Encrypt and store a user's SEGA ID credentials."""
    f = _get_fernet()
    encrypted = f.encrypt(password.encode()).decode()
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        await db.execute("""
            INSERT INTO segaid_accounts (discord_user_id, username, encrypted_password, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                username = excluded.username,
                encrypted_password = excluded.encrypted_password,
                updated_at = CURRENT_TIMESTAMP
        """, (discord_user_id, username, encrypted))
        await db.commit()


async def get_segaid_account(discord_user_id: str) -> Optional[Dict[str, str]]:
    """Retrieve and decrypt a user's SEGA ID credentials."""
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username, encrypted_password FROM segaid_accounts WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        f = _get_fernet()
        return {"username": row[0], "password": f.decrypt(row[1].encode()).decode()}


async def delete_segaid_account(discord_user_id: str) -> bool:
    """Remove a user's stored SEGA ID credentials. Returns True if deleted."""
    async with aiosqlite.connect(SEGAID_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM segaid_accounts WHERE discord_user_id = ?",
            (discord_user_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
