"""
MaiMai Discord Song Quiz Admin Bot
Separate bot process that hosts admin-only commands.
"""

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("ADMIN_DISCORD_TOKEN")

# Bot setup
intents = discord.Intents.default()

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    """Called when the admin bot is ready and connected to Discord."""
    print(f"Admin bot connected as {bot.user}")
    print(f"Connected to {len(bot.guilds)} server(s)")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.tree.command(name="sync", description="Force sync slash commands to this server (bot owner only)")
async def sync_commands(interaction: discord.Interaction):
    """Force sync slash commands to this server (bot owner only)."""
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    try:
        bot.tree.copy_global_to(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.response.send_message(f"✅ Synced {len(synced)} command(s) to this server!")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to sync: {e}")


async def setup_hook():
    """Setup hook to load admin cog before bot starts."""
    try:
        await bot.load_extension("cogs.admin")
        print("Loaded admin cog")
    except Exception as e:
        print(f"Error loading admin cog: {e}")


# Assign setup hook
bot.setup_hook = setup_hook


def main():
    """Main entry point for the admin bot."""
    if not TOKEN:
        print("Error: ADMIN_DISCORD_TOKEN not found in .env file")
        print("Please add ADMIN_DISCORD_TOKEN to your .env file")
        return

    print("Starting MaiMai Quiz Admin Bot...")

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("Error: Invalid admin bot token")
    except Exception as e:
        print(f"Error starting admin bot: {e}")


if __name__ == "__main__":
    main()
