"""
MaiMai Discord Song Quiz Bot
Main entry point for the Discord bot.
"""

import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Required to read messages for guessing
intents.messages = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    print(f'✅ {bot.user} has connected to Discord!')
    print(f'📊 Connected to {len(bot.guilds)} server(s)')
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')

@bot.event
async def on_message(message):
    """Listen to all messages for guess processing."""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Process commands (needed for bot framework)
    await bot.process_commands(message)

async def setup_hook():
    """Setup hook to load cogs before bot starts."""
    try:
        await bot.load_extension('cogs.quiz')
        print("✅ Loaded quiz cog")
    except Exception as e:
        print(f"❌ Error loading quiz cog: {e}")
    try:
        await bot.load_extension('cogs.admin')
        print("✅ Loaded admin cog")
    except Exception as e:
        print(f"❌ Error loading admin cog: {e}")

# Assign setup hook
bot.setup_hook = setup_hook

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

def main():
    """Main entry point."""
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in .env file")
        print("Please create a .env file with your Discord bot token:")
        print("DISCORD_TOKEN=your_token_here")
        return
    
    print("🚀 Starting MaiMai Quiz Bot...")
    
    # Start the bot
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Error: Invalid Discord token")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")

if __name__ == "__main__":
    main()
