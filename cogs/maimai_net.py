"""
maimai NET integration commands for linking accounts and fetching play data.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from utils.database import save_token, get_token, delete_token, save_scores, delete_scores, has_scores, get_score_summary
from utils.maimai_scraper import validate_token, fetch_all_scores, match_scores_to_songs


class MaimaiNetCog(commands.Cog):
    """Commands for linking maimai NET account and managing play data."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="loginhelp", description="How to find your maimai NET cookie for /login")
    async def loginhelp(self, interaction: discord.Interaction):
        """Show instructions for obtaining the clal cookie."""
        embed = discord.Embed(
            title="How to Link Your maimai NET Account",
            description="Follow these steps to get your `clal` cookie:",
            color=discord.Color.blue(),
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

        embed.set_footer(text="Your token is stored encrypted and never shared. Use /logout to remove it.")
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

    @app_commands.command(name="logout", description="Unlink your maimai NET account and remove stored data")
    async def logout(self, interaction: discord.Interaction):
        """Remove stored token and cached scores."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        token_deleted = await delete_token(user_id)
        await delete_scores(user_id)

        if token_deleted:
            await interaction.followup.send(
                "Your maimai NET token and cached scores have been removed.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "No linked account found. Use `/login` to link your maimai NET account.",
                ephemeral=True,
            )

    @app_commands.command(name="fetch", description="Fetch your latest scores from maimai NET")
    async def fetch(self, interaction: discord.Interaction):
        """Fetch scores from maimai NET and cache them locally."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)

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
        try:
            raw_scores = await fetch_all_scores(token, on_progress=on_progress)
        except Exception as e:
            await interaction.followup.send(
                f"Error fetching scores: {e}\nYour token may have expired. Try `/login` with a fresh cookie.",
                ephemeral=True,
            )
            return

        if not raw_scores:
            await interaction.followup.send(
                "No scores found. Your token may have expired. Try `/login` with a fresh cookie.",
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
            description=f"Successfully fetched your maimai NET scores.",
            color=discord.Color.green(),
        )

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


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(MaimaiNetCog(bot))
