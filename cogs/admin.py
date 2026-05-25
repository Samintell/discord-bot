"""
Admin commands for managing bot configuration (translations, romaji overrides, aliases).
Restricted to a specific admin user ID.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from pathlib import Path
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_manager import (
    load_translations, add_translation, remove_translation,
    load_romaji_overrides, add_romaji_override, remove_romaji_override,
    load_aliases, add_alias, remove_alias,
)
from utils.admin_signals import emit_admin_signal
from utils.song_loader import _get_all_songs, clear_song_cache
from utils.database import set_profile_coins_balance


def is_admin():
    """Check decorator that restricts commands to the bot owner."""
    async def predicate(interaction: discord.Interaction) -> bool:
        app_info = await interaction.client.application_info()
        if app_info.team:
            owner_ids = {m.id for m in app_info.team.members}
        else:
            owner_ids = {app_info.owner.id}
        if interaction.user.id not in owner_ids:
            raise app_commands.CheckFailure("You are not authorized to use this command.")
        return True
    return app_commands.check(predicate)


def _resolve_song_id(identifier: str) -> Optional[str]:
    """Resolve a song identifier (song_id, title, or romaji) to a song_id.

    Returns the song_id if found, None otherwise.
    """
    all_songs = _get_all_songs()
    identifier_lower = identifier.lower()

    for song in all_songs:
        if song.get('song_id', '').lower() == identifier_lower:
            return song['song_id']

    for song in all_songs:
        if song.get('title', '').lower() == identifier_lower:
            return song['song_id']

    for song in all_songs:
        romaji = song.get('romaji', '')
        if romaji and romaji.lower() == identifier_lower:
            return song['song_id']

    return None


def _get_song_display(song_id: str) -> str:
    """Get a display name for a song_id (title + romaji if available)."""
    all_songs = _get_all_songs()
    for song in all_songs:
        if song.get('song_id') == song_id:
            title = song.get('title', song_id)
            romaji = song.get('romaji', '')
            if romaji and romaji != title:
                return f"{title} ({romaji})"
            return title
    return song_id


class AdminCog(commands.Cog):
    """Admin commands for managing bot configuration."""

    def __init__(self, bot):
        self.bot = bot

    # ==================== TRANSLATION COMMANDS ====================

    translation_group = app_commands.Group(
        name="translation",
        description="Manage English translations for song titles (admin only)",
        default_permissions=discord.Permissions()
    )

    @translation_group.command(name="add", description="Add or update an English translation")
    @app_commands.describe(
        japanese_title="The Japanese song title",
        english="The English translation"
    )
    @is_admin()
    async def translation_add(self, interaction: discord.Interaction, japanese_title: str, english: str):
        add_translation(japanese_title, english)
        await interaction.response.send_message(
            f"**Translation added/updated:**\n`{japanese_title}` -> `{english}`",
            ephemeral=True
        )

    @translation_group.command(name="remove", description="Remove an English translation")
    @app_commands.describe(japanese_title="The Japanese song title to remove")
    @is_admin()
    async def translation_remove(self, interaction: discord.Interaction, japanese_title: str):
        if remove_translation(japanese_title):
            await interaction.response.send_message(
                f"**Translation removed:** `{japanese_title}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No translation found for `{japanese_title}`",
                ephemeral=True
            )

    @translation_group.command(name="list", description="List all English translations")
    @is_admin()
    async def translation_list(self, interaction: discord.Interaction):
        translations = load_translations()
        if not translations:
            await interaction.response.send_message("No translations configured.", ephemeral=True)
            return

        # Paginate to avoid message length limits (Discord max: 2000 chars)
        lines = [f"`{jp}` -> `{en}`" for jp, en in sorted(translations.items())]
        pages = []
        current_page = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 1800:
                pages.append("\n".join(current_page))
                current_page = []
                current_len = 0
            current_page.append(line)
            current_len += len(line) + 1
        if current_page:
            pages.append("\n".join(current_page))

        header = f"**Translations ({len(translations)} total):**\n"
        await interaction.response.send_message(
            header + pages[0] + (f"\n\n*Page 1/{len(pages)}*" if len(pages) > 1 else ""),
            ephemeral=True
        )
        for i, page in enumerate(pages[1:], 2):
            await interaction.followup.send(
                page + f"\n\n*Page {i}/{len(pages)}*",
                ephemeral=True
            )

    # ==================== ROMAJI COMMANDS ====================

    romaji_group = app_commands.Group(
        name="romaji",
        description="Manage romaji overrides for song titles (admin only)",
        default_permissions=discord.Permissions()
    )

    @romaji_group.command(name="add", description="Add or update a romaji override")
    @app_commands.describe(
        title="The song title (as it appears in the database)",
        romaji="The correct romaji reading"
    )
    @is_admin()
    async def romaji_add(self, interaction: discord.Interaction, title: str, romaji: str):
        add_romaji_override(title, romaji)
        await interaction.response.send_message(
            f"**Romaji override added/updated:**\n`{title}` -> `{romaji}`",
            ephemeral=True
        )

    @romaji_group.command(name="remove", description="Remove a romaji override")
    @app_commands.describe(title="The song title to remove the override for")
    @is_admin()
    async def romaji_remove(self, interaction: discord.Interaction, title: str):
        if remove_romaji_override(title):
            await interaction.response.send_message(
                f"**Romaji override removed:** `{title}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No romaji override found for `{title}`",
                ephemeral=True
            )

    @romaji_group.command(name="list", description="List all romaji overrides")
    @is_admin()
    async def romaji_list(self, interaction: discord.Interaction):
        overrides = load_romaji_overrides()
        if not overrides:
            await interaction.response.send_message("No romaji overrides configured.", ephemeral=True)
            return

        lines = [f"`{title}` -> `{romaji}`" for title, romaji in sorted(overrides.items())]
        pages = []
        current_page = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 1800:
                pages.append("\n".join(current_page))
                current_page = []
                current_len = 0
            current_page.append(line)
            current_len += len(line) + 1
        if current_page:
            pages.append("\n".join(current_page))

        header = f"**Romaji Overrides ({len(overrides)} total):**\n"
        await interaction.response.send_message(
            header + pages[0] + (f"\n\n*Page 1/{len(pages)}*" if len(pages) > 1 else ""),
            ephemeral=True
        )
        for i, page in enumerate(pages[1:], 2):
            await interaction.followup.send(
                page + f"\n\n*Page {i}/{len(pages)}*",
                ephemeral=True
            )

    # ==================== ALIAS COMMANDS ====================

    alias_group = app_commands.Group(
        name="alias",
        description="Manage song aliases for quiz guessing (admin only)",
        default_permissions=discord.Permissions()
    )

    @alias_group.command(name="add", description="Add an alias for a song")
    @app_commands.describe(
        song="Song identifier (song_id, Japanese title, or romaji)",
        alias="The alias text to add"
    )
    @is_admin()
    async def alias_add(self, interaction: discord.Interaction, song: str, alias: str):
        song_id = _resolve_song_id(song)
        if not song_id:
            await interaction.response.send_message(
                f"Could not find a song matching `{song}`",
                ephemeral=True
            )
            return

        add_alias(song_id, alias)
        display = _get_song_display(song_id)
        await interaction.response.send_message(
            f"**Alias added:**\n{display}\n-> `{alias}`",
            ephemeral=True
        )

    @alias_group.command(name="remove", description="Remove an alias from a song")
    @app_commands.describe(
        song="Song identifier (song_id, Japanese title, or romaji)",
        alias="The alias text to remove"
    )
    @is_admin()
    async def alias_remove(self, interaction: discord.Interaction, song: str, alias: str):
        song_id = _resolve_song_id(song)
        if not song_id:
            await interaction.response.send_message(
                f"Could not find a song matching `{song}`",
                ephemeral=True
            )
            return

        if remove_alias(song_id, alias):
            display = _get_song_display(song_id)
            await interaction.response.send_message(
                f"**Alias removed:**\n{display}\n-> `{alias}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No alias `{alias}` found for that song.",
                ephemeral=True
            )

    @alias_group.command(name="list", description="List aliases for a song or all songs")
    @app_commands.describe(
        song="Song identifier (optional - leave blank to list all)"
    )
    @is_admin()
    async def alias_list(self, interaction: discord.Interaction, song: Optional[str] = None):
        all_aliases = load_aliases()

        if not all_aliases:
            await interaction.response.send_message("No aliases configured.", ephemeral=True)
            return

        if song:
            song_id = _resolve_song_id(song)
            if not song_id:
                await interaction.response.send_message(
                    f"Could not find a song matching `{song}`",
                    ephemeral=True
                )
                return

            aliases = all_aliases.get(song_id, [])
            if not aliases:
                await interaction.response.send_message(
                    f"No aliases for {_get_song_display(song_id)}",
                    ephemeral=True
                )
                return

            display = _get_song_display(song_id)
            alias_text = "\n".join(f"- `{a}`" for a in aliases)
            await interaction.response.send_message(
                f"**Aliases for {display}:**\n{alias_text}",
                ephemeral=True
            )
        else:
            lines = []
            for sid, aliases in sorted(all_aliases.items()):
                display = _get_song_display(sid)
                alias_str = ", ".join(f"`{a}`" for a in aliases)
                lines.append(f"**{display}:** {alias_str}")

            pages = []
            current_page = []
            current_len = 0
            for line in lines:
                if current_len + len(line) + 1 > 1800:
                    pages.append("\n".join(current_page))
                    current_page = []
                    current_len = 0
                current_page.append(line)
                current_len += len(line) + 1
            if current_page:
                pages.append("\n".join(current_page))

            header = f"**All Song Aliases ({len(all_aliases)} songs):**\n"
            await interaction.response.send_message(
                header + pages[0] + (f"\n\n*Page 1/{len(pages)}*" if len(pages) > 1 else ""),
                ephemeral=True
            )
            for i, page in enumerate(pages[1:], 2):
                await interaction.followup.send(
                    page + f"\n\n*Page {i}/{len(pages)}*",
                    ephemeral=True
                )

    # ==================== REPORT COMMANDS ====================

    coins_group = app_commands.Group(
        name="coins",
        description="Manage profile currency (admin only)",
        default_permissions=discord.Permissions()
    )

    @coins_group.command(name="set", description="Set a user's maimiles balance")
    @app_commands.describe(
        user="User to update",
        amount="New maimiles balance"
    )
    @is_admin()
    async def coins_set(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if amount < 0:
            await interaction.response.send_message("Amount must be 0 or higher.", ephemeral=True)
            return

        await set_profile_coins_balance(str(user.id), amount)
        await interaction.response.send_message(
            f"Set maimiles for {user.mention} to {amount}.",
            ephemeral=True
        )

    report_group = app_commands.Group(
        name="reports",
        description="View and clear user-submitted reports (admin only)",
        default_permissions=discord.Permissions()
    )

    @report_group.command(name="translations", description="View reported translation issues")
    @is_admin()
    async def reports_translations(self, interaction: discord.Interaction):
        project_root = Path(__file__).parent.parent
        submissions_file = project_root / "translation_submissions.json"

        if not submissions_file.exists():
            await interaction.response.send_message("No translation reports found.", ephemeral=True)
            return

        try:
            import json
            with open(submissions_file, 'r', encoding='utf-8') as f:
                submissions = json.load(f)
        except (json.JSONDecodeError, IOError):
            await interaction.response.send_message("Error reading translation reports.", ephemeral=True)
            return

        if not submissions:
            await interaction.response.send_message("No translation reports found.", ephemeral=True)
            return

        lines = []
        for i, sub in enumerate(submissions, 1):
            timestamp = sub.get('timestamp', '?')[:10]
            user = sub.get('user_name', '?')
            title = sub.get('japanese_title', '?')
            suggestion = sub.get('suggested_translation', '?')
            server = sub.get('server_name', '?')
            lines.append(f"**{i}.** `{title}` -> `{suggestion}`\n   By {user} in {server} ({timestamp})")

        pages = []
        current_page = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 1800:
                pages.append("\n".join(current_page))
                current_page = []
                current_len = 0
            current_page.append(line)
            current_len += len(line) + 1
        if current_page:
            pages.append("\n".join(current_page))

        header = f"**Translation Reports ({len(submissions)} total):**\n"
        await interaction.response.send_message(
            header + pages[0] + (f"\n\n*Page 1/{len(pages)}*" if len(pages) > 1 else ""),
            ephemeral=True
        )
        for i, page in enumerate(pages[1:], 2):
            await interaction.followup.send(
                page + f"\n\n*Page {i}/{len(pages)}*",
                ephemeral=True
            )

    @report_group.command(name="audio", description="View reported audio issues")
    @is_admin()
    async def reports_audio(self, interaction: discord.Interaction):
        project_root = Path(__file__).parent.parent
        submissions_file = project_root / "audio_submissions.json"

        if not submissions_file.exists():
            await interaction.response.send_message("No audio reports found.", ephemeral=True)
            return

        try:
            import json
            with open(submissions_file, 'r', encoding='utf-8') as f:
                submissions = json.load(f)
        except (json.JSONDecodeError, IOError):
            await interaction.response.send_message("Error reading audio reports.", ephemeral=True)
            return

        if not submissions:
            await interaction.response.send_message("No audio reports found.", ephemeral=True)
            return

        lines = []
        for i, sub in enumerate(submissions, 1):
            timestamp = sub.get('timestamp', '?')[:10]
            user = sub.get('user_name', '?')
            title = sub.get('song_title', '?')
            issue = sub.get('issue_description', '?')
            server = sub.get('server_name', '?')
            lines.append(f"**{i}.** `{title}`: {issue}\n   By {user} in {server} ({timestamp})")

        pages = []
        current_page = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 1800:
                pages.append("\n".join(current_page))
                current_page = []
                current_len = 0
            current_page.append(line)
            current_len += len(line) + 1
        if current_page:
            pages.append("\n".join(current_page))

        header = f"**Audio Reports ({len(submissions)} total):**\n"
        await interaction.response.send_message(
            header + pages[0] + (f"\n\n*Page 1/{len(pages)}*" if len(pages) > 1 else ""),
            ephemeral=True
        )
        for i, page in enumerate(pages[1:], 2):
            await interaction.followup.send(
                page + f"\n\n*Page {i}/{len(pages)}*",
                ephemeral=True
            )

    @report_group.command(name="clear", description="Clear all reports of a given type")
    @app_commands.describe(
        report_type="Which reports to clear"
    )
    @app_commands.choices(report_type=[
        app_commands.Choice(name="Translation reports", value="translations"),
        app_commands.Choice(name="Audio reports", value="audio"),
        app_commands.Choice(name="All reports", value="all"),
    ])
    @is_admin()
    async def reports_clear(self, interaction: discord.Interaction, report_type: str):
        import json
        project_root = Path(__file__).parent.parent
        cleared = []

        if report_type in ('translations', 'all'):
            trans_file = project_root / "translation_submissions.json"
            if trans_file.exists():
                with open(trans_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                cleared.append("translation")

        if report_type in ('audio', 'all'):
            audio_file = project_root / "audio_submissions.json"
            if audio_file.exists():
                with open(audio_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                cleared.append("audio")

        if cleared:
            await interaction.response.send_message(
                f"**Cleared {', '.join(cleared)} reports.**",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "No report files found to clear.",
                ephemeral=True
            )

    # ==================== REFRESH COMMAND ====================

    @app_commands.command(name="refresh", description="Run scripts/convert_data.py and reload song database (admin only)")
    @app_commands.default_permissions()
    @is_admin()
    async def refresh_data(self, interaction: discord.Interaction):
        """Run scripts/convert_data.py to re-download/regenerate output.json, then clear the song cache."""
        import asyncio

        await interaction.response.defer(ephemeral=True)

        try:
            project_root = Path(__file__).parent.parent
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(project_root / "scripts" / "convert_data.py"),
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            output_text = stdout.decode("utf-8", errors="replace").strip()
            error_text = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode == 0:
                # Clear the cached song data so the next quiz loads fresh data
                clear_song_cache()

                try:
                    emit_admin_signal("reload_songs")
                except Exception as signal_error:
                    print(f"Warning: Failed to emit admin signal: {signal_error}")

                # Truncate output for Discord message limits
                summary = output_text[-1500:] if len(output_text) > 1500 else output_text
                await interaction.followup.send(
                    f"**Song database refreshed successfully.**\n```\n{summary}\n```",
                    ephemeral=True,
                )
            else:
                err_summary = error_text[-1000:] if len(error_text) > 1000 else error_text
                await interaction.followup.send(
                    f"**scripts/convert_data.py failed (exit code {process.returncode}):**\n```\n{err_summary}\n```",
                    ephemeral=True,
                )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "**scripts/convert_data.py timed out after 120 seconds.**",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"**Error running scripts/convert_data.py:** {e}",
                ephemeral=True,
            )

    # ==================== ERROR HANDLING ====================

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            try:
                await interaction.response.send_message(
                    "You are not authorized to use this command.",
                    ephemeral=True
                )
            except discord.errors.NotFound:
                pass
        else:
            try:
                await interaction.response.send_message(
                    f"An error occurred: {error}",
                    ephemeral=True
                )
            except discord.errors.NotFound:
                pass


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(AdminCog(bot))
