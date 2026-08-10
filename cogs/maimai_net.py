"""
maimai NET integration commands for linking accounts and fetching play data.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import time

from utils.database import save_scores, delete_scores, has_scores, get_score_summary, get_profile, set_user_language
from utils.maimai_scraper import validate_token, fetch_all_scores, match_scores_to_songs
from utils.segaid_db import save_token, get_token, delete_token, save_segaid_account, delete_segaid_account
from utils.segaid_login import login_with_segaid, try_refresh_with_segaid
from utils.b50_calculator import B50Calculator
from utils.b50_renderer import B50Renderer
import discord.app_commands as app_commands


class SegaIDLoginModal(discord.ui.Modal):
    """Modal for entering SEGA ID credentials.

    Not the recommended login method - using /login with a clal cookie is
    safer because the cookie can be revoked without exposing your password.
    """

    username = discord.ui.TextInput(
        label="SEGA ID Username",
        placeholder="Enter your SEGA ID username",
        max_length=64,
    )
    password = discord.ui.TextInput(
        label="SEGA ID Password (not recommended)",
        placeholder="Recommended: use /login with your clal cookie instead",
        max_length=128,
    )

    def __init__(self):
        super().__init__(title="SEGA ID Login (Not Recommended)")

    async def on_submit(self, interaction: discord.Interaction):
        """Perform the SEGA ID login with the entered credentials."""
        # Always respond ephemerally so credentials are never visible to others
        await interaction.response.defer(ephemeral=True)

        username = self.username.value.strip()
        password = self.password.value
        user_id = str(interaction.user.id)

        # Log in via the SEGA ID auth gateway and get a clal session cookie
        ok, message, clal = await login_with_segaid(username, password)
        if not ok or not clal:
            await interaction.followup.send(f"Login failed: {message}", ephemeral=True)
            return

        # Validate the session and get the player name
        is_valid, validate_msg = await validate_token(clal)
        if not is_valid:
            await interaction.followup.send(f"Login failed: {validate_msg}", ephemeral=True)
            return

        try:
            await save_token(user_id, clal)
            await save_segaid_account(user_id, username, password)
        except RuntimeError as e:
            await interaction.followup.send(
                f"Configuration error: {e}\nThe bot owner needs to set TOKEN_SECRET in the .env file.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="SEGA ID Linked",
            description=(
                f"{validate_msg}\n\n"
                f"Your SEGA ID login is stored encrypted in a separate database and your "
                f"session has been saved. Run `/fetch` to download your scores.\n\n"
                f"If your session expires, the bot can refresh it automatically with `/fetch`."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Your password is encrypted and never visible to others.")
        await interaction.followup.send(embed=embed, ephemeral=True)


class MaimaiNetCog(commands.Cog):
    """Commands for linking maimai NET account and managing play data."""

    COOLDOWN_SECONDS = 30

    def __init__(self, bot):
        self.bot = bot
        self._last_used: dict[str, float] = {}

    def _check_cooldown(self, user_id: str) -> bool:
        """Return True if the user is on cooldown, otherwise record the call."""
        now = time.monotonic()
        last = self._last_used.get(user_id)
        if last is not None and now - last < self.COOLDOWN_SECONDS:
            return True
        self._last_used[user_id] = now
        return False

    def _cooldown_remaining(self, user_id: str) -> int:
        """Return seconds remaining on the cooldown for a user."""
        last = self._last_used.get(user_id)
        if last is None:
            return 0
        remaining = self.COOLDOWN_SECONDS - (time.monotonic() - last)
        return max(0, int(remaining) + 1)

    @app_commands.command(name="loginhelp", description="How to link your maimai NET account")
    async def loginhelp(self, interaction: discord.Interaction):
        """Show instructions for linking a maimai NET account."""
        embed = discord.Embed(
            title="How to Link Your maimai NET Account",
            description="There are two ways to link your account:",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Option 1: SEGA ID Login (Not Recommended)",
            value=(
                "Run `/login_segaid` and enter your SEGA ID **username** and **password** "
                "in the popup window.\n"
                "**Not recommended** - use Option 2 (clal cookie) whenever possible. "
                "A cookie can be revoked without exposing your password."
            ),
            inline=False,
        )
        embed.add_field(
            name="Option 2: clal Cookie",
            value="Follow the steps below to get your `clal` cookie instead:",
            inline=False,
        )
        embed.add_field(
            name="Step 1: Log in to maimai NET",
            value="Go to [maimaidx-eng.com](https://maimaidx-eng.com/) and log in with your SEGA ID.",
            inline=False,
        )
        embed.add_field(
            name="Step 2: Go to the Auth Page",
            value="Visit [lng-tgk-aime-gw.am-all.net/common_auth/](https://lng-tgk-aime-gw.am-all.net/common_auth/)",
            inline=False,
        )
        embed.add_field(
            name="Step 3: Open Developer Tools",
            value="Press `F12` → **Application** tab (Chrome) or **Storage** tab (Firefox) → **Cookies**",
            inline=False,
        )
        embed.add_field(
            name="Step 4: Copy the Cookie",
            value=(
                "Select `https://lng-tgk-aime-gw.am-all.net`.\n"
                "Find the cookie named `clal` and copy its **Value**."
            ),
            inline=False,
        )
        embed.add_field(
            name="Step 5: Use /login",
            value="Run `/login` and paste your `clal` value as the token.\n**Keep this value private!**",
            inline=False,
        )

        embed.set_footer(text="Login data is stored encrypted and never shared. Use /logout to remove it.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="login", description="Link your maimai NET (International) account using your clal cookie")
    @app_commands.describe(
        token="Your clal cookie value from lng-tgk-aime-gw.am-all.net. Use /loginhelp for instructions."
    )
    async def login(self, interaction: discord.Interaction, token: str):
        """Store a maimai NET authentication cookie."""
        # Always respond ephemerally so the token is never visible to others
        await interaction.response.defer(ephemeral=True)

        # Strip common prefixes users might accidentally include
        clean_token = token.strip()
        if clean_token.startswith("clal="):
            clean_token = clean_token[5:]

        # Validate the token against maimai NET
        is_valid, message = await validate_token(clean_token)

        if not is_valid:
            await interaction.followup.send(f"Login failed: {message}", ephemeral=True)
            return

        # Store the encrypted token
        user_id = str(interaction.user.id)
        try:
            await save_token(user_id, clean_token)
        except RuntimeError as e:
            await interaction.followup.send(
                f"Configuration error: {e}\nThe bot owner needs to set TOKEN_SECRET in the .env file.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="maimai NET Linked",
            description=f"{message}\n\nYour token has been saved. Run `/fetch` to download your scores.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Your token is stored encrypted and is never visible to others.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="login_segaid", description="Link your maimai NET account with SEGA ID (not recommended - use /login instead)")
    async def login_segaid(self, interaction: discord.Interaction):
        """Open a modal to enter SEGA ID credentials."""
        await interaction.response.send_modal(SegaIDLoginModal())

    @app_commands.command(name="logout", description="Unlink your maimai NET account and remove stored data")
    async def logout(self, interaction: discord.Interaction):
        """Remove stored token and cached scores."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        token_deleted = await delete_token(user_id)
        await delete_scores(user_id)
        segaid_deleted = await delete_segaid_account(user_id)

        if token_deleted or segaid_deleted:
            await interaction.followup.send(
                "Your maimai NET session, SEGA ID login, and cached scores have been removed.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "No linked account found. Use `/login` or `/login_segaid` to link your maimai NET account.",
                ephemeral=True,
            )

    @app_commands.command(name="fetch", description="Fetch your latest scores from maimai NET")
    async def fetch(self, interaction: discord.Interaction):
        """Fetch scores from maimai NET and cache them locally."""
        user_id = str(interaction.user.id)

        if self._check_cooldown(user_id):
            remaining = self._cooldown_remaining(user_id)
            await interaction.response.send_message(
                f"⏳ Please wait {remaining}s before using `/fetch` again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Get stored token
        try:
            token = await get_token(user_id)
        except RuntimeError as e:
            await interaction.followup.send(
                f"Configuration error: {e}\nThe bot owner needs to set TOKEN_SECRET in the .env file.",
                ephemeral=True,
            )
            return

        if not token:
            await interaction.followup.send(
                "No linked account found. Use `/login` first to link your maimai NET account.",
                ephemeral=True,
            )
            return

        # Track progress
        progress_parts = []

        async def on_progress(diff_name, count):
            progress_parts.append(f"{diff_name}: {count} scores")

        # Fetch scores
        raw_scores = []
        fetch_error = None
        try:
            raw_scores = await fetch_all_scores(token, on_progress=on_progress)
        except Exception as e:
            fetch_error = e

        # If the session expired, try refreshing automatically via SEGA ID login
        refreshed = False
        if not raw_scores:
            new_token = await try_refresh_with_segaid(user_id)
            if new_token:
                progress_parts = []
                raw_scores = await fetch_all_scores(new_token, on_progress=on_progress)
                refreshed = True

        if fetch_error and not raw_scores:
            await interaction.followup.send(
                f"Error fetching scores: {fetch_error}\nYour token may have expired. Try `/login` with a fresh cookie.",
                ephemeral=True,
            )
            return

        if not raw_scores:
            await interaction.followup.send(
                "No scores found. Your token may have expired. Try `/login` or `/login_segaid`.",
                ephemeral=True,
            )
            return

        # Match to output.json
        matched_scores, unmatched_count = match_scores_to_songs(raw_scores)

        # Save to database
        saved_count = await save_scores(user_id, matched_scores)

        # Build summary
        embed = discord.Embed(
            title="Scores Fetched",
            description="Successfully fetched your maimai NET scores.",
            color=discord.Color.green(),
        )

        if refreshed:
            embed.add_field(name="Session Refreshed", value="Your expired session was renewed automatically via SEGA ID login.", inline=False)

        progress_text = "\n".join(progress_parts) if progress_parts else "No data"
        embed.add_field(name="Fetched", value=progress_text, inline=False)
        embed.add_field(name="Total Scores", value=str(len(raw_scores)), inline=True)
        embed.add_field(name="Matched to Songs", value=str(saved_count), inline=True)
        if unmatched_count > 0:
            embed.add_field(name="Unmatched", value=str(unmatched_count), inline=True)

        embed.set_footer(text="You can now use score filters with /quiz (e.g., score_difficulty:Master score_rank:S)")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mystats", description="Show a summary of your cached maimai NET scores")
    async def mystats(self, interaction: discord.Interaction):
        """Display a summary of the user's cached scores."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        summary = await get_score_summary(user_id)

        if not summary:
            await interaction.followup.send(
                "No cached scores found. Use `/login` and `/fetch` to download your scores from maimai NET.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Your maimai Score Summary",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Unique Songs", value=str(summary["unique_songs"]), inline=True)
        embed.add_field(name="Total Entries", value=str(summary["total_scores"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer

        # Difficulty breakdown
        diff_order = ["basic", "advanced", "expert", "master", "remaster"]
        diff_lines = []
        for diff in diff_order:
            count = summary["by_difficulty"].get(diff, 0)
            if count > 0:
                diff_lines.append(f"**{diff.capitalize()}**: {count}")
        if diff_lines:
            embed.add_field(name="By Difficulty", value="\n".join(diff_lines), inline=True)

        # Rank distribution (expert/master/remaster only)
        rank_lines = []
        for rank_name in ["SSS+", "SSS", "SS+", "SS", "S+", "S", "AAA", "AA", "A"]:
            count = summary["rank_counts"].get(rank_name, 0)
            if count > 0:
                rank_lines.append(f"**{rank_name}+**: {count} songs")
        if rank_lines:
            embed.add_field(name="Rank Distribution (Expert+)", value="\n".join(rank_lines[:6]), inline=True)

        embed.set_footer(text="Ranks show songs at or above that rank on Expert/Master/Remaster")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="b50", description="Generate your maimai DX best 50 rating chart")
    @app_commands.describe(
        language="Optional: Override your preferred song title language for this chart"
    )
    @app_commands.choices(language=[
        app_commands.Choice(name="Japanese", value="japanese"),
        app_commands.Choice(name="Romaji", value="romaji"),
        app_commands.Choice(name="English", value="english")
    ])
    async def b50(self, interaction: discord.Interaction, language: Optional[discord.app_commands.Choice[str]] = None):
        """Generate and display the user's best 50 scores."""
        user_id = str(interaction.user.id)

        if self._check_cooldown(user_id):
            remaining = self._cooldown_remaining(user_id)
            await interaction.response.send_message(
                f"⏳ Please wait {remaining}s before using `/b50` again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)

        status_msg = await interaction.followup.send("🔄 Loading your profile...", ephemeral=False)

        # Load user profile for language, banner, partner
        profile = await get_profile(user_id)
        
        pref_language = language.value if language else profile.get("name_language", "japanese")
        banner_id = profile.get("banner_id")
        partner_id = profile.get("partner_id")
        header_id = profile.get("header_id")
        
        # Calculate B50
        calculator = B50Calculator(user_id)

        async def on_progress(diff_name, count):
            await status_msg.edit(
                content=f"🔄 Fetching scores from maimai NET... **{diff_name}**: {count} scores"
            )

        async def on_fetch_complete():
            await status_msg.edit(content="📊 Calculating ratings...")

        top_15, top_35, total_rating = await calculator.get_b50(
            on_progress=on_progress,
            on_fetch_complete=on_fetch_complete,
        )
        
        if not top_15 and not top_35:
            await status_msg.edit(content="No scores found! Please use `/login` and `/fetch` first to download your scores.")
            return
            
        await status_msg.edit(content="🎨 Rendering your B50 chart...")

        # Get user avatar
        avatar_bytes = None
        if interaction.user.display_avatar:
            try:
                avatar_bytes = await interaction.user.display_avatar.read()
            except Exception:
                pass
                
        # Render image
        username = interaction.user.display_name
        renderer = B50Renderer(
            username=username,
            language=pref_language,
            top_15=top_15,
            top_35=top_35,
            total_rating=total_rating,
            avatar_bytes=avatar_bytes,
            banner_id=banner_id,
            partner_id=partner_id,
            header_id=header_id
        )
        
        img_buffer = renderer.render()
        
        file = discord.File(fp=img_buffer, filename="b50.png")
        
        msg = ""
        if calculator.refreshed_session:
            msg = "🔄 *Your expired maimai NET session was refreshed automatically via SEGA ID.*"
        if calculator.used_cache and calculator.error_message:
            msg = f"⚠️ *{calculator.error_message}*"
            
        await status_msg.edit(content=msg, attachments=[file])

    # Note: If this is an existing cog with other commands, a command group might be better for settings.
    # We will just add a settings command here for language.
    @app_commands.command(name="set_language", description="Set your preferred language for song titles")
    @app_commands.choices(language=[
        app_commands.Choice(name="Japanese", value="japanese"),
        app_commands.Choice(name="Romaji", value="romaji"),
        app_commands.Choice(name="English", value="english")
    ])
    async def set_language(self, interaction: discord.Interaction, language: app_commands.Choice[str]):
        """Set preferred language for song titles."""
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        
        await set_user_language(user_id, language.value)
        await interaction.followup.send(f"Successfully set your preferred language to **{language.name}**.", ephemeral=True)


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(MaimaiNetCog(bot))
