"""
Quiz game cog with commands for starting, playing, and managing MaiMai song quiz games.
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import random
import io
import json
from PIL import Image
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.song_loader import load_songs, get_song_image_path, get_song_audio_path
from utils.matcher import check_answer
from utils.constants import CATEGORIES, VERSIONS, CATEGORY_MAPPING, VERSION_MAPPING


class SkipButton(ui.View):
    """View with a skip button for quiz rounds."""
    
    def __init__(self, cog, channel: discord.TextChannel, host_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.channel = channel
        self.host_id = host_id
        self.skipped = False
    
    @ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle skip button press."""
        game = self.cog.active_games.get(self.channel.id)
        
        if not game:
            await interaction.response.send_message("❌ No active game!", ephemeral=True)
            return
        
        # Only host can skip
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Only the host can skip!", ephemeral=True)
            return
        
        if self.skipped:
            await interaction.response.send_message("❌ Already skipping!", ephemeral=True)
            return
        
        self.skipped = True
        button.disabled = True
        
        # Acknowledge the interaction
        await interaction.response.send_message("⏭️ Skipping...", ephemeral=True)
        
        # Perform skip logic
        await self.cog.perform_skip(self.channel, game)
    
    async def on_timeout(self):
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True


class PlayAgainButton(ui.View):
    """View with a play again button for game end."""
    
    def __init__(self, cog, channel: discord.TextChannel, host_id: int, game_config: dict, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.channel = channel
        self.host_id = host_id
        self.game_config = game_config
        self.clicked = False
    
    @ui.button(label="Play Again", style=discord.ButtonStyle.primary, emoji="🔁")
    async def play_again_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle play again button press."""
        # Only host can restart
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Only the original host can restart the game!", ephemeral=True)
            return
        
        # Check if a game is already running
        if self.channel.id in self.cog.active_games or self.channel.id in self.cog.creating_games:
            await interaction.response.send_message("❌ A game is already active in this channel!", ephemeral=True)
            return
        
        if self.clicked:
            await interaction.response.send_message("❌ Already starting a new game!", ephemeral=True)
            return
        
        self.clicked = True
        button.disabled = True
        
        # Acknowledge the interaction
        await interaction.response.send_message("🔁 Starting new game with same settings...", ephemeral=True)
        
        # Start new game with same config
        await self.cog.start_game_with_config(self.channel, interaction.user.id, self.game_config)
    
    async def on_timeout(self):
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True

class GameSession:
    """Represents an active quiz game session."""
    
    def __init__(self, channel_id: int, host_id: int, config: dict):
        self.channel_id = channel_id
        self.host_id = host_id
        self.mode = config.get('mode', 'audio')  # 'image' or 'audio'
        self.answer_type = config.get('answer_type', 'title')  # 'title' or 'artist'
        self.time_limit = config.get('time_limit', 60)
        self.total_rounds = config.get('rounds', 10)
        self.snippet_length = config.get('snippet_length', 10)  # Audio snippet length in seconds
        self.image_difficulty = config.get('image_difficulty', 'easy')  # 'easy', 'medium', 'hard'
        
        # Store original config for replay (without song_pool which changes)
        self.original_config = {
            'mode': self.mode,
            'answer_type': self.answer_type,
            'time_limit': self.time_limit,
            'rounds': self.total_rounds,
            'snippet_length': self.snippet_length,
            'image_difficulty': self.image_difficulty,
            'categories': config.get('categories'),
            'versions': config.get('versions')
        }
        
        self.current_round = 0
        self.song_pool: List[dict] = config.get('song_pool', [])
        self.current_song: Optional[dict] = None
        self.scores: Dict[int, int] = {}  # user_id -> score
        self.round_start_time: Optional[datetime] = None
        self.timeout_task: Optional[asyncio.Task] = None
        self.answered = False  # Track if someone answered this round
        
    def next_song(self) -> Optional[dict]:
        """Get the next song from the pool."""
        if not self.song_pool:
            return None
        self.current_round += 1
        self.current_song = self.song_pool.pop(0)
        self.answered = False
        return self.current_song
    
    def add_score(self, user_id: int, points: int = 1):
        """Add points to a user's score."""
        self.scores[user_id] = self.scores.get(user_id, 0) + points
    
    def get_leaderboard(self) -> List[tuple]:
        """Get sorted leaderboard (user_id, score)."""
        return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)


class QuizCog(commands.Cog):
    """Quiz game commands and functionality."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_games: Dict[int, GameSession] = {}  # channel_id -> GameSession
        self.creating_games: set = set()  # Track channels currently creating games
    
    async def send_voice_message(self, channel: discord.TextChannel, file_path: str, duration_secs: float) -> bool:
        """Send an audio file as a Discord voice message using low-level API."""
        import aiohttp
        import base64
        
        try:
            # Read the file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Generate a simple waveform (256 bytes of audio levels)
            # This is a simplified waveform - Discord expects base64-encoded bytes
            waveform_bytes = bytes([128] * 256)  # Flat waveform
            waveform_b64 = base64.b64encode(waveform_bytes).decode('ascii')
            
            # Prepare the multipart form data
            form = aiohttp.FormData()
            
            # Add the file
            form.add_field(
                'files[0]',
                file_data,
                filename='voice-message.ogg',
                content_type='audio/ogg'
            )
            
            # Add the payload JSON with voice message flag (1 << 13 = 8192)
            import json
            payload = {
                'flags': 8192,  # IS_VOICE_MESSAGE flag
                'attachments': [{
                    'id': 0,
                    'filename': 'voice-message.ogg',
                    'duration_secs': duration_secs,
                    'waveform': waveform_b64
                }]
            }
            form.add_field('payload_json', json.dumps(payload))
            
            # Send via Discord's HTTP client
            url = f"https://discord.com/api/v10/channels/{channel.id}/messages"
            headers = {
                'Authorization': f'Bot {self.bot.http.token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=form, headers=headers) as resp:
                    if resp.status in (200, 201):
                        return True
                    else:
                        error_text = await resp.text()
                        print(f"Voice message API error {resp.status}: {error_text}")
                        return False
                        
        except Exception as e:
            print(f"Error sending voice message: {e}")
            return False
    
    def format_answer(self, song: dict, answer_type: str) -> str:
        """Format the answer display with Japanese, Romaji, and English."""
        if answer_type == 'artist':
            return song.get('artist', 'Unknown')
        
        if answer_type == 'difficulty':
            level = song.get('level', 0)
            difficulty_type = song.get('difficulty', 'master')
            return f"{level} ({difficulty_type})"
        
        # For title, show Japanese, Romaji, and English (if available)
        title = song.get('title', '')
        romaji = song.get('romaji', '')
        english = song.get('english', '')
        
        parts = [title]
        if romaji and romaji != title:
            parts.append(romaji)
        if english and english != title and english != romaji:
            parts.append(f"({english})")
        
        return ' / '.join(parts)
    
    def get_difficulty_display(self, song: dict) -> str:
        """Get difficulty level display string."""
        level = song.get('level', 0)
        difficulty_type = song.get('difficulty', 'master')
        return f"Level {level} ({difficulty_type})"
    
    def crop_image_for_difficulty(self, image_path: str, difficulty: str) -> io.BytesIO:
        """Crop image based on difficulty level.
        
        Args:
            image_path: Path to the original image
            difficulty: 'easy' (full), 'medium' (25%), or 'hard' (10%)
            
        Returns:
            BytesIO object containing the cropped PNG image
        """
        with Image.open(image_path) as img:
            width, height = img.size
            
            if difficulty == 'easy':
                # Full image
                crop_width, crop_height = width, height
                left, top = 0, 0
            elif difficulty == 'medium':
                # 25% of image (50% width x 50% height)
                crop_width = width // 2
                crop_height = height // 2
                # Random position
                left = random.randint(0, width - crop_width)
                top = random.randint(0, height - crop_height)
            else:  # hard
                # 10% of image area (~31.6% of each dimension)
                scale = 0.316  # sqrt(0.1) ≈ 0.316
                crop_width = int(width * scale)
                crop_height = int(height * scale)
                # Random position
                left = random.randint(0, width - crop_width)
                top = random.randint(0, height - crop_height)
            
            # Crop the image
            cropped = img.crop((left, top, left + crop_width, top + crop_height))
            
            # Save to BytesIO
            output = io.BytesIO()
            cropped.save(output, format='PNG')
            output.seek(0)
            return output

    @app_commands.command(name="quiz", description="Start a MaiMai song quiz game")
    @app_commands.describe(
        mode="Quiz mode",
        answer_type="What to guess",
        rounds="Number of rounds to play (1-50)",
        time_limit="Seconds per round (10-300)",
        snippet_length="Audio snippet length in seconds (5-30, only for audio mode)",
        image_difficulty="Image visibility (easy=full, medium=25%, hard=10%)",
        categories="Comma-separated (e.g. 'POPS＆アニメ,東方Project') or leave empty for all",
        versions="Comma-separated (e.g. 'FESTiVAL,BUDDiES,PRiSM') or leave empty for all"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Image", value="image"),
        app_commands.Choice(name="Audio", value="audio")
    ])
    @app_commands.choices(answer_type=[
        app_commands.Choice(name="Title", value="title"),
        app_commands.Choice(name="Artist", value="artist"),
        app_commands.Choice(name="Difficulty Level", value="difficulty")
    ])
    @app_commands.choices(image_difficulty=[
        app_commands.Choice(name="Easy (full image)", value="easy"),
        app_commands.Choice(name="Medium (25% of image)", value="medium"),
        app_commands.Choice(name="Hard (10% of image)", value="hard")
    ])
    async def quiz_start(
        self,
        interaction: discord.Interaction,
        mode: str = "audio",
        answer_type: str = "title",
        rounds: int = 10,
        time_limit: int = 20,
        snippet_length: int = 10,
        image_difficulty: str = "easy",
        categories: Optional[str] = None,
        versions: Optional[str] = None
    ):
        """Start a new quiz game."""
        channel_id = interaction.channel_id
        
        # Check if game already active or being created in this channel
        if channel_id in self.active_games or channel_id in self.creating_games:
            try:
                await interaction.response.send_message("❌ A game is already active in this channel!", ephemeral=True)
            except discord.errors.NotFound:
                pass
            return
        
        # Mark this channel as creating a game
        self.creating_games.add(channel_id)
        
        # Validate parameters
        if mode not in ['image', 'audio']:
            self.creating_games.discard(channel_id)
            await interaction.response.send_message("❌ Mode must be 'image' or 'audio'", ephemeral=True)
            return
        
        if answer_type not in ['title', 'artist', 'difficulty']:
            self.creating_games.discard(channel_id)
            await interaction.response.send_message("❌ Answer type must be 'title', 'artist', or 'difficulty'", ephemeral=True)
            return
        
        if rounds < 1 or rounds > 50:
            self.creating_games.discard(channel_id)
            await interaction.response.send_message("❌ Rounds must be between 1 and 50", ephemeral=True)
            return
        
        if time_limit < 10 or time_limit > 300:
            self.creating_games.discard(channel_id)
            await interaction.response.send_message("❌ Time limit must be between 10 and 300 seconds", ephemeral=True)
            return
        
        if snippet_length < 5 or snippet_length > 30:
            self.creating_games.discard(channel_id)
            await interaction.response.send_message("❌ Snippet length must be between 5 and 30 seconds", ephemeral=True)
            return
        
        # Respond immediately to avoid timeout
        try:
            await interaction.response.send_message("⏳ Loading songs...", ephemeral=True)
        except discord.errors.NotFound:
            # Interaction expired - abort to prevent duplicates
            self.creating_games.discard(channel_id)
            return
        
        # Parse comma-separated categories and versions
        category_list = None
        version_list = None
        
        if categories:
            input_cats = [c.strip() for c in categories.split(',')]
            category_list = []
            invalid_cats = []
            
            for cat in input_cats:
                # Try to map English/Japanese to official Japanese name
                mapped = CATEGORY_MAPPING.get(cat.lower())
                if mapped:
                    category_list.append(mapped)
                else:
                    invalid_cats.append(cat)
            
            if invalid_cats:
                valid_list = "\n- ".join([f"{jp} ({en})" for jp, en in CATEGORIES.items()])
                await interaction.channel.send(f"❌ Invalid categories: {', '.join(invalid_cats)}\n\n**Valid categories:**\n- {valid_list}")
                self.creating_games.discard(channel_id)
                return
        
        if versions:
            input_vers = [v.strip() for v in versions.split(',')]
            version_list = []
            
            for ver in input_vers:
                # Try to map English/Japanese to official Japanese name
                mapped = VERSION_MAPPING.get(ver.lower())
                if mapped:
                    version_list.append(mapped)
                else:
                    # If not found, use original (for partial matches)
                    version_list.append(ver)
        
        try:
            # Load all master difficulty songs
            all_songs = load_songs(difficulty="master")
            
            # Filter by categories if specified
            if category_list:
                all_songs = [s for s in all_songs if s.get('category') in category_list]
            
            # Filter by versions if specified
            if version_list:
                all_songs = [s for s in all_songs if s.get('version') in version_list]
            
            songs = all_songs
            
            if not songs:
                await interaction.channel.send("❌ No songs found with the specified filters!")
                self.creating_games.discard(channel_id)
                return
            
            if len(songs) < rounds:
                rounds = len(songs)
            
            # Shuffle and select songs
            random.shuffle(songs)
            song_pool = songs[:rounds]
            
            # Filter by available media files
            if mode == 'image':
                song_pool = [s for s in song_pool if get_song_image_path(s)]
            elif mode == 'audio':
                song_pool = [s for s in song_pool if get_song_audio_path(s)]
            
            if not song_pool:
                await interaction.channel.send(f"❌ No songs with {mode} files available!")
                self.creating_games.discard(channel_id)
                return
            
            if len(song_pool) < rounds:
                rounds = len(song_pool)
            
            # Create game session
            config = {
                'mode': mode,
                'answer_type': answer_type,
                'time_limit': time_limit,
                'rounds': rounds,
                'snippet_length': snippet_length,
                'image_difficulty': image_difficulty,
                'song_pool': song_pool,
                'categories': categories,  # Store original input for replay
                'versions': versions  # Store original input for replay
            }
            
            game = GameSession(channel_id, interaction.user.id, config)
            self.active_games[channel_id] = game
            self.creating_games.discard(channel_id)  # Remove from creating set
            
            # Send game start message
            difficulty_text = ""
            if mode == 'image':
                difficulty_labels = {'easy': 'Easy (full image)', 'medium': 'Medium (25%)', 'hard': 'Hard (10%)'}
                difficulty_text = f"\n**Image Difficulty:** {difficulty_labels.get(image_difficulty, image_difficulty)}"
            
            embed = discord.Embed(
                title="🎵 MaiMai Song Quiz Started!",
                description=f"**Mode:** {mode.title()}\n**Guess:** {answer_type.title()}\n**Rounds:** {rounds}\n**Time per round:** {time_limit}s{difficulty_text}",
                color=discord.Color.blue()
            )
            
            if category_list:
                embed.add_field(name="Categories", value=", ".join(category_list), inline=False)
            if version_list:
                embed.add_field(name="Versions", value=", ".join(version_list), inline=False)
            
            embed.set_footer(text="Get ready! First round starting in 3 seconds...")
            
            await interaction.channel.send(embed=embed)
            
            # Start first round after delay
            await asyncio.sleep(3)
            await self.start_round(interaction.channel)
            
        except Exception as e:
            await interaction.channel.send(f"❌ Error starting game: {e}")
            self.creating_games.discard(channel_id)
            if channel_id in self.active_games:
                del self.active_games[channel_id]
    
    async def create_audio_snippet(self, audio_path: str, snippet_length: int, channel_id: int) -> Optional[str]:
        """Create a random audio snippet from the full audio file."""
        import subprocess
        from pathlib import Path
        import shutil
        
        # Get the project root directory (parent of cogs/)
        project_root = Path(__file__).parent.parent
        
        try:
            # Check if ffmpeg and ffprobe are available
            if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
                return None
            
            # Get audio duration using ffprobe
            probe_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(audio_path)
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return None
            
            duration = float(result.stdout.strip())
            
            # If song is shorter than snippet length, use full song
            if duration <= snippet_length:
                return str(audio_path)
            
            # Pick random start time
            max_start = duration - snippet_length
            start_time = random.uniform(0, max_start)
            
            # Create snippet with ffmpeg in OGG Opus format for voice message
            # Use absolute path based on project root
            snippet_dir = project_root / 'audio' / 'snippets'
            snippet_dir.mkdir(parents=True, exist_ok=True)
            
            snippet_path = snippet_dir / f"snippet_{channel_id}_{int(datetime.now().timestamp())}.ogg"
            
            # Use loudnorm filter to normalize audio volume for consistent playback
            # Target: -16 LUFS (standard for streaming), with true peak at -1.5 dB
            ffmpeg_cmd = [
                'ffmpeg',
                '-ss', str(start_time),
                '-i', str(audio_path),
                '-t', str(snippet_length),
                '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
                '-c:a', 'libopus',
                '-b:a', '64k',
                '-vbr', 'on',
                '-compression_level', '10',
                '-application', 'voip',
                '-y',
                str(snippet_path)
            ]
            
            subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)
            
            if snippet_path.exists():
                return str(snippet_path)
            return None
            
        except Exception as e:
            return None
    
    async def start_round(self, channel: discord.TextChannel):
        """Start a new round in the game."""
        game = self.active_games.get(channel.id)
        if not game:
            return
        
        song = game.next_song()
        if not song:
            await self.end_game(channel)
            return
        
        game.round_start_time = datetime.now()
        
        # Create skip button view
        skip_view = SkipButton(self, channel, game.host_id, timeout=game.time_limit + 10)
        
        # Create round embed
        embed = discord.Embed(
            title=f"🎮 Round {game.current_round}/{game.total_rounds}",
            description=f"**Guess the {game.answer_type}!**\nType your answer in chat.",
            color=discord.Color.green()
        )
        
        # Add hint based on answer type
        if game.answer_type == 'artist':
            embed.add_field(name="🎤 Artist", value="???", inline=True)
            embed.add_field(name="📝 Title", value=song.get('romaji') or song.get('title'), inline=True)
        elif game.answer_type == 'difficulty':
            embed.add_field(name=" Difficulty", value="???", inline=True)
        else:  # title mode
            embed.add_field(name="📝 Title", value="???", inline=True)
        
        embed.add_field(name="⏱️ Time Limit", value=f"{game.time_limit}s", inline=True)
        
        # Add media
        if game.mode == 'image':
            image_path = get_song_image_path(song)
            if image_path:
                # Crop image based on difficulty
                cropped_image = self.crop_image_for_difficulty(image_path, game.image_difficulty)
                file = discord.File(cropped_image, filename="cover.png")
                embed.set_image(url="attachment://cover.png")
                await channel.send(embed=embed, file=file, view=skip_view)
            else:
                await channel.send(embed=embed, view=skip_view)
        elif game.mode == 'audio':
            # Send embed first with skip button
            await channel.send(embed=embed, view=skip_view)
            
            # Then send audio snippet as voice message
            audio_path = get_song_audio_path(song)
            if audio_path:
                # Create audio snippet
                snippet_path = await self.create_audio_snippet(audio_path, game.snippet_length, channel.id)
                if snippet_path:
                    try:
                        # Try to send as voice message
                        success = await self.send_voice_message(channel, snippet_path, game.snippet_length)
                        if not success:
                            # Fall back to regular file
                            file = discord.File(snippet_path, filename="snippet.ogg")
                            await channel.send(file=file)
                    except Exception as e:
                        print(f"Error sending audio: {e}")
                        # Fall back to regular file
                        try:
                            file = discord.File(snippet_path, filename="snippet.ogg")
                            await channel.send(file=file)
                        except:
                            pass
                    
                    # Clean up snippet file if it's not the original
                    if snippet_path != str(audio_path):
                        try:
                            Path(snippet_path).unlink()
                        except:
                            pass
                else:
                    # Fall back to full audio if snippet creation fails
                    file = discord.File(audio_path, filename="song.mp3")
                    await channel.send(file=file)
            else:
                pass  # No audio file available
        
        # Start timeout timer
        game.timeout_task = asyncio.create_task(self.round_timeout(channel))
    
    async def round_timeout(self, channel: discord.TextChannel):
        """Handle round timeout."""
        game = self.active_games.get(channel.id)
        if not game:
            return
        
        try:
            await asyncio.sleep(game.time_limit)
            
            # If already answered, don't proceed
            if game.answered:
                return
            
            # Time's up!
            song = game.current_song
            correct_answer = self.format_answer(song, game.answer_type)
            artist = song.get('artist', 'Unknown')
            version = song.get('version', 'Unknown')
            
            embed = discord.Embed(
                title="⏰ Time's Up!",
                description=f"No one guessed correctly!",
                color=discord.Color.red()
            )
            embed.add_field(name="✅ Correct Answer", value=correct_answer, inline=False)
            if game.answer_type == 'title':
                embed.add_field(name="Artist", value=artist, inline=False)
                embed.add_field(name="Difficulty", value=self.get_difficulty_display(song), inline=True)
                embed.add_field(name="Version", value=version, inline=True)
            elif game.answer_type == 'artist':
                embed.add_field(name="Difficulty", value=self.get_difficulty_display(song), inline=True)
                embed.add_field(name="Version", value=version, inline=True)
            elif game.answer_type == 'difficulty':
                title_display = song.get('romaji') or song.get('title', 'Unknown')
                embed.add_field(name="Title", value=title_display, inline=False)
                embed.add_field(name="Artist", value=artist, inline=False)
                embed.add_field(name="Version", value=version, inline=True)
            
            # Add song image
            image_path = get_song_image_path(song)
            if image_path:
                file = discord.File(image_path, filename="answer.png")
                embed.set_thumbnail(url="attachment://answer.png")
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
            
            # Wait before next round
            await asyncio.sleep(3)
            
            # Check if game still exists before starting next round
            if channel.id in self.active_games:
                await self.start_round(channel)
            
        except asyncio.CancelledError:
            pass  # Task was cancelled (someone answered)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for guesses in active game channels."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if there's an active game in this channel
        game = self.active_games.get(message.channel.id)
        if not game or not game.current_song:
            return
        
        # Check if already answered
        if game.answered:
            return
        
        # Check answer
        if check_answer(message.content, game.current_song, game.answer_type):
            game.answered = True
            
            # Cancel timeout
            if game.timeout_task:
                game.timeout_task.cancel()
            
            # Calculate response time
            response_time = (datetime.now() - game.round_start_time).total_seconds()
            
            # Add score
            game.add_score(message.author.id, 1)
            
            # Get correct answer
            song = game.current_song
            correct_answer = self.format_answer(song, game.answer_type)
            artist = song.get('artist', 'Unknown')
            version = song.get('version', 'Unknown')
            
            # Send success message
            embed = discord.Embed(
                title="✅ Correct!",
                description=f"**{message.author.mention}** got it in **{response_time:.2f}s**!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Answer", value=correct_answer, inline=False)
            if game.answer_type == 'difficulty':
                title_display = song.get('romaji') or song.get('title', 'Unknown')
                embed.add_field(name="Title", value=title_display, inline=False)
                embed.add_field(name="Artist", value=artist, inline=False)
                embed.add_field(name="Version", value=version, inline=True)
            else:
                embed.add_field(name="Difficulty", value=self.get_difficulty_display(song), inline=True)
                embed.add_field(name="Version", value=version, inline=True)
            if game.answer_type == 'title':
                embed.add_field(name="Artist", value=artist, inline=False)
            embed.add_field(name="Score", value=f"{game.scores[message.author.id]} point(s)", inline=True)
            
            # Add song image
            image_path = get_song_image_path(song)
            if image_path:
                file = discord.File(image_path, filename="answer.png")
                embed.set_thumbnail(url="attachment://answer.png")
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)
            
            # Wait before next round
            await asyncio.sleep(3)
            
            # Check if game still exists before starting next round
            if message.channel.id in self.active_games:
                await self.start_round(message.channel)
    
    @app_commands.command(name="skip", description="Vote to skip the current song")
    async def skip(self, interaction: discord.Interaction):
        """Skip the current round."""
        game = self.active_games.get(interaction.channel_id)
        
        if not game:
            try:
                await interaction.response.send_message("❌ No active game in this channel!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("❌ No active game in this channel!")
            return
        
        # Only host can skip for now (can implement voting later)
        if interaction.user.id != game.host_id:
            try:
                await interaction.response.send_message("❌ Only the host can skip rounds!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("❌ Only the host can skip rounds!")
            return
        
        # Respond to interaction immediately
        try:
            await interaction.response.send_message("⏭️ Skipping...", ephemeral=True)
        except discord.errors.NotFound:
            pass  # Interaction already expired, continue anyway
        
        # Perform the skip
        await self.perform_skip(interaction.channel, game)
    
    async def perform_skip(self, channel: discord.TextChannel, game: GameSession):
        """Perform skip logic - shared between button and command."""
        # Cancel timeout
        if game.timeout_task:
            game.timeout_task.cancel()
        
        game.answered = True  # Mark as answered to prevent timeout message
        
        # Show the answer
        song = game.current_song
        if song:
            correct_answer = self.format_answer(song, game.answer_type)
            artist = song.get('artist', 'Unknown')
            version = song.get('version', 'Unknown')
            
            embed = discord.Embed(
                title="⏭️ Skipped",
                description="Moving to next round...",
                color=discord.Color.orange()
            )
            embed.add_field(name="✅ Correct Answer", value=correct_answer, inline=False)
            if game.answer_type == 'title':
                embed.add_field(name="Artist", value=artist, inline=False)
                embed.add_field(name="Difficulty", value=self.get_difficulty_display(song), inline=True)
                embed.add_field(name="Version", value=version, inline=True)
            elif game.answer_type == 'artist':
                embed.add_field(name="Difficulty", value=self.get_difficulty_display(song), inline=True)
                embed.add_field(name="Version", value=version, inline=True)
            elif game.answer_type == 'difficulty':
                title_display = song.get('romaji') or song.get('title', 'Unknown')
                embed.add_field(name="Title", value=title_display, inline=False)
                embed.add_field(name="Artist", value=artist, inline=False)
                embed.add_field(name="Version", value=version, inline=True)
            
            # Add song image
            image_path = get_song_image_path(song)
            if image_path:
                file = discord.File(image_path, filename="answer.png")
                embed.set_thumbnail(url="attachment://answer.png")
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
        else:
            await channel.send("⏭️ Skipping to next round...")
        
        await asyncio.sleep(2)
        
        # Check if game still exists before starting next round
        if channel.id in self.active_games:
            await self.start_round(channel)
    
    @app_commands.command(name="leaderboard", description="Show current game leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show the leaderboard."""
        game = self.active_games.get(interaction.channel_id)
        
        if not game:
            try:
                await interaction.response.send_message("❌ No active game in this channel!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("❌ No active game in this channel!")
            return
        
        if not game.scores:
            try:
                await interaction.response.send_message("📊 No scores yet!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("📊 No scores yet!")
            return
        
        leaderboard = game.get_leaderboard()
        
        embed = discord.Embed(
            title="📊 Leaderboard",
            description=f"Round {game.current_round}/{game.total_rounds}",
            color=discord.Color.purple()
        )
        
        for i, (user_id, score) in enumerate(leaderboard[:10], 1):
            user = await self.bot.fetch_user(user_id)
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            embed.add_field(name=f"{medal} {user.display_name}", value=f"{score} point(s)", inline=False)
        
        try:
            await interaction.response.send_message(embed=embed)
        except discord.errors.NotFound:
            await interaction.channel.send(embed=embed)
    
    @app_commands.command(name="stop", description="Stop the current quiz game")
    async def stop(self, interaction: discord.Interaction):
        """Stop the active game."""
        game = self.active_games.get(interaction.channel_id)
        
        if not game:
            try:
                await interaction.response.send_message("❌ No active game in this channel!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("❌ No active game in this channel!")
            return
        
        # Only host can stop
        if interaction.user.id != game.host_id:
            try:
                await interaction.response.send_message("❌ Only the host can stop the game!", ephemeral=True)
            except discord.errors.NotFound:
                await interaction.channel.send("❌ Only the host can stop the game!")
            return
        
        try:
            await interaction.response.send_message("🛑 Stopping game...")
        except discord.errors.NotFound:
            await interaction.channel.send("🛑 Stopping game...")
        await self.end_game(interaction.channel, cancelled=True)
    
    async def end_game(self, channel: discord.TextChannel, cancelled: bool = False):
        """End the game and show final results."""
        game = self.active_games.get(channel.id)
        if not game:
            # Ensure cleanup even if game not found
            self.active_games.pop(channel.id, None)
            self.creating_games.discard(channel.id)
            return
        
        # Cancel any pending timeout
        if game.timeout_task:
            game.timeout_task.cancel()
        
        try:
            # Create final results embed
            embed = discord.Embed(
                title="🏁 Game Over!" if not cancelled else "🛑 Game Stopped",
                description=f"Played {game.current_round} round(s)",
                color=discord.Color.gold() if not cancelled else discord.Color.red()
            )
            
            if game.scores:
                leaderboard = game.get_leaderboard()
                
                # Add top 3
                for i, (user_id, score) in enumerate(leaderboard[:3], 1):
                    display_name = None
                    # Try getting from guild members first
                    if channel.guild:
                        member = channel.guild.get_member(user_id)
                        if member:
                            display_name = member.display_name
                    # Try bot's user cache
                    if not display_name:
                        user = self.bot.get_user(user_id)
                        if user:
                            display_name = user.display_name
                    # Last resort: fetch from API
                    if not display_name:
                        try:
                            user = await self.bot.fetch_user(user_id)
                            display_name = user.display_name
                        except:
                            display_name = f"User {user_id}"
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    embed.add_field(name=f"{medal} {display_name}", value=f"{score} point(s)", inline=False)
                
                # Show total participants
                embed.set_footer(text=f"Total players: {len(game.scores)}")
            else:
                embed.description += "\n\nNo scores recorded."
            
            # Create Play Again button with original config
            play_again_view = PlayAgainButton(
                cog=self,
                channel=channel,
                host_id=game.host_id,
                game_config=game.original_config,
                timeout=60
            )
            
            await channel.send(embed=embed, view=play_again_view)
        except Exception as e:
            print(f"Error in end_game: {e}")
        finally:
            # Always remove game from active games and creating games
            self.active_games.pop(channel.id, None)
            self.creating_games.discard(channel.id)
    
    async def start_game_with_config(self, channel: discord.TextChannel, host_id: int, config: dict):
        """Start a new game with the given config (used by Play Again button)."""
        if channel.id in self.active_games or channel.id in self.creating_games:
            await channel.send("❌ A game is already active in this channel!")
            return
        
        self.creating_games.add(channel.id)
        
        try:
            # Load all master difficulty songs
            all_songs = load_songs(difficulty="master")
            
            if not all_songs:
                await channel.send("❌ No songs found in database!")
                self.creating_games.discard(channel.id)
                return
            
            # Apply category filter if it was used
            category_list = None
            if config.get('categories'):
                input_cats = [c.strip() for c in config['categories'].split(',')]
                category_list = []
                for cat in input_cats:
                    mapped = CATEGORY_MAPPING.get(cat.lower())
                    if mapped:
                        category_list.append(mapped)
                
                if category_list:
                    all_songs = [s for s in all_songs if s.get('category') in category_list]
            
            # Apply version filter if it was used
            version_list = None
            if config.get('versions'):
                input_vers = [v.strip() for v in config['versions'].split(',')]
                version_list = []
                for ver in input_vers:
                    mapped = VERSION_MAPPING.get(ver.lower())
                    if mapped:
                        version_list.append(mapped)
                    else:
                        version_list.append(ver)
                
                if version_list:
                    all_songs = [s for s in all_songs if s.get('version') in version_list]
            
            songs = all_songs
            
            if not songs:
                await channel.send("❌ No songs found with the specified filters!")
                self.creating_games.discard(channel.id)
                return
            
            rounds = config['rounds']
            if len(songs) < rounds:
                rounds = len(songs)
            
            # Shuffle and select songs
            random.shuffle(songs)
            song_pool = songs[:rounds]
            
            # Filter by available media files
            mode = config['mode']
            if mode == 'image':
                song_pool = [s for s in song_pool if get_song_image_path(s)]
            elif mode == 'audio':
                song_pool = [s for s in song_pool if get_song_audio_path(s)]
            
            if not song_pool:
                await channel.send(f"❌ No songs with {mode} files available!")
                self.creating_games.discard(channel.id)
                return
            
            if len(song_pool) < rounds:
                rounds = len(song_pool)
            
            # Update config with new song pool
            new_config = config.copy()
            new_config['rounds'] = rounds
            new_config['song_pool'] = song_pool
            
            # Create new game session
            game = GameSession(channel.id, host_id, new_config)
            self.active_games[channel.id] = game
            self.creating_games.discard(channel.id)
            
            # Send start message
            difficulty_text = ""
            if mode == 'image':
                difficulty_labels = {'easy': 'Easy (full image)', 'medium': 'Medium (25%)', 'hard': 'Hard (10%)'}
                difficulty_text = f"\n**Image Difficulty:** {difficulty_labels.get(config.get('image_difficulty', 'easy'), config.get('image_difficulty', 'easy'))}"
            
            embed = discord.Embed(
                title="🔁 Quiz Restarting!",
                description=f"**Mode:** {mode.title()}\n**Guess:** {config['answer_type'].title()}\n**Rounds:** {rounds}\n**Time per round:** {config['time_limit']}s{difficulty_text}",
                color=discord.Color.green()
            )
            
            if category_list:
                embed.add_field(name="Categories", value=", ".join(category_list), inline=False)
            if version_list:
                embed.add_field(name="Versions", value=", ".join(version_list), inline=False)
            
            embed.set_footer(text="Get ready! First round starting in 3 seconds...")
            
            await channel.send(embed=embed)
            
            # Start the first round after delay
            await asyncio.sleep(3)
            await self.start_round(channel)
            
        except Exception as e:
            print(f"Error starting game with config: {e}")
            import traceback
            traceback.print_exc()
            await channel.send(f"❌ Error starting game: {str(e)}")
            self.creating_games.discard(channel.id)
            self.active_games.pop(channel.id, None)
    
    @app_commands.command(name="filters", description="Show available categories and versions for filtering")
    async def show_filters(self, interaction: discord.Interaction):
        """Show available filter options."""
        embed = discord.Embed(
            title="📋 Available Filters",
            description="Use these in `/quiz` with comma-separated values (case-insensitive, English or Japanese)",
            color=discord.Color.blue()
        )
        
        # Add categories with English translations
        categories_text = "\n".join([f"• **{en}** ({jp})" for jp, en in CATEGORIES.items()])
        embed.add_field(name="Categories", value=categories_text, inline=False)
        
        # Add versions (split into two columns)
        version_items = list(VERSIONS.items())
        mid = len(version_items) // 2
        versions_col1 = "\n".join([f"• **{en}** ({jp})" for jp, en in version_items[:mid]])
        versions_col2 = "\n".join([f"• **{en}** ({jp})" for jp, en in version_items[mid:]])
        embed.add_field(name="Versions (1/2)", value=versions_col1, inline=True)
        embed.add_field(name="Versions (2/2)", value=versions_col2, inline=True)
        
        embed.set_footer(text="Example: /quiz categories:pops,touhou versions:festival,buddies")
        
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            await interaction.channel.send(embed=embed)
    
    @app_commands.command(name="help", description="Show help information about the quiz bot")
    async def help_command(self, interaction: discord.Interaction):
        """Display comprehensive help information."""
        embed = discord.Embed(
            title="🎮 MaiMai Quiz Bot Help",
            description="Welcome to the MaiMai song quiz bot! Test your knowledge of MaiMai songs.",
            color=discord.Color.blue()
        )
        
        # Quiz command
        embed.add_field(
            name="🎯 /quiz",
            value=(
                "Start a new quiz game with customizable options:\n"
                "• **mode**: `Image` (show cover) or `Audio` (play snippet)\n"
                "• **answer_type**: `Title`, `Artist`, or `Difficulty Level`\n"
                "• **rounds**: Number of songs (1-50, default: 10)\n"
                "• **time_limit**: Seconds per round (15-180, default: 60)\n"
                "• **categories**: Filter by genre (comma-separated)\n"
                "• **versions**: Filter by game version (comma-separated)\n"
                "• **snippet_length**: Audio length in seconds (5-30, default: 10)\n\n"
                "**Example**: `/quiz mode:Image answer_type:Title rounds:5`"
            ),
            inline=False
        )
        
        # Gameplay commands
        embed.add_field(
            name="🎮 During Quiz",
            value=(
                "• Type your guess directly in chat (no command needed)\n"
                "• `/skip` - Vote to skip current song (majority vote)\n"
                "• `/leaderboard` - View current scores\n"
                "• `/stop` - End the game (host only)"
            ),
            inline=False
        )
        
        # Info commands
        embed.add_field(
            name="📋 Information",
            value=(
                "• `/filters` - Show available categories and versions\n"
                "• `/help` - Show this help message"
            ),
            inline=False
        )
        
        # Reporting commands
        embed.add_field(
            name="🔧 Report Issues",
            value=(
                "• `/report_translation` - Report incorrect English translations\n"
                "• `/report_audio` - Report audio issues (wrong/missing/poor quality)"
            ),
            inline=False
        )
        
        # Tips
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Accepts Japanese, romaji, or English answers\n"
                "• Partial matches accepted for titles/artists (fuzzy matching)\n"
                "• Difficulty guesses must be exact (e.g., 13.7)\n"
                "• First correct answer wins the point\n"
                "• Multiple games can run in different channels"
            ),
            inline=False
        )
        
        embed.set_footer(text="Have fun and enjoy the quiz! 🎵")
        
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            await interaction.channel.send(embed=embed)
    
    @app_commands.command(name="report_translation", description="Report an incorrect English translation")
    @app_commands.describe(
        japanese_title="The Japanese song title (as shown in the quiz)",
        suggested_translation="Your suggested English translation"
    )
    async def report_translation(self, interaction: discord.Interaction, japanese_title: str, suggested_translation: str):
        """Allow players to submit translation corrections."""
        # Create submission entry
        submission = {
            "timestamp": datetime.now().isoformat(),
            "user_id": interaction.user.id,
            "user_name": f"{interaction.user.name}#{interaction.user.discriminator}",
            "japanese_title": japanese_title,
            "suggested_translation": suggested_translation,
            "server_id": interaction.guild_id if interaction.guild else None,
            "server_name": interaction.guild.name if interaction.guild else "DM"
        }
        
        # Save to file
        submissions_file = Path("translation_submissions.json")
        submissions = []
        
        # Load existing submissions if file exists
        if submissions_file.exists():
            try:
                with open(submissions_file, 'r', encoding='utf-8') as f:
                    submissions = json.load(f)
            except (json.JSONDecodeError, IOError):
                submissions = []
        
        # Add new submission
        submissions.append(submission)
        
        # Save updated submissions
        try:
            with open(submissions_file, 'w', encoding='utf-8') as f:
                json.dump(submissions, f, indent=2, ensure_ascii=False)
            
            embed = discord.Embed(
                title="✅ Translation Submitted",
                description="Thank you for helping improve the translation database!",
                color=discord.Color.green()
            )
            embed.add_field(name="Japanese Title", value=japanese_title, inline=False)
            embed.add_field(name="Your Suggestion", value=suggested_translation, inline=False)
            embed.set_footer(text="Your submission will be reviewed by the bot maintainer.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except IOError as e:
            await interaction.response.send_message(
                f"❌ Failed to save submission: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="report_audio", description="Report an incorrect or missing audio file")
    @app_commands.describe(
        song_title="The song title (Japanese or romaji)",
        issue_description="Describe the issue (e.g., 'wrong song', 'audio missing', 'poor quality')"
    )
    async def report_audio(self, interaction: discord.Interaction, song_title: str, issue_description: str):
        """Allow players to report audio issues."""
        # Create submission entry
        submission = {
            "timestamp": datetime.now().isoformat(),
            "user_id": interaction.user.id,
            "user_name": f"{interaction.user.name}#{interaction.user.discriminator}",
            "song_title": song_title,
            "issue_description": issue_description,
            "server_id": interaction.guild_id if interaction.guild else None,
            "server_name": interaction.guild.name if interaction.guild else "DM"
        }
        
        # Save to file
        submissions_file = Path("audio_submissions.json")
        submissions = []
        
        # Load existing submissions if file exists
        if submissions_file.exists():
            try:
                with open(submissions_file, 'r', encoding='utf-8') as f:
                    submissions = json.load(f)
            except (json.JSONDecodeError, IOError):
                submissions = []
        
        # Add new submission
        submissions.append(submission)
        
        # Save updated submissions
        try:
            with open(submissions_file, 'w', encoding='utf-8') as f:
                json.dump(submissions, f, indent=2, ensure_ascii=False)
            
            embed = discord.Embed(
                title="✅ Audio Issue Reported",
                description="Thank you for helping improve the audio database!",
                color=discord.Color.green()
            )
            embed.add_field(name="Song Title", value=song_title, inline=False)
            embed.add_field(name="Issue", value=issue_description, inline=False)
            embed.set_footer(text="Your report will be reviewed by the bot maintainer.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except IOError as e:
            await interaction.response.send_message(
                f"❌ Failed to save report: {e}",
                ephemeral=True
            )
    
    # ==================== PREFIX COMMANDS (q>) ====================
    
    @commands.command(name="quiz")
    async def prefix_quiz(self, ctx, mode: str = "audio", answer_type: str = "title", 
                          rounds: int = 10, time_limit: int = 20, snippet_length: int = 10,
                          image_difficulty: str = "easy"):
        """Start a quiz game with prefix command. Usage: q>quiz [mode] [answer_type] [rounds] [time_limit] [snippet_length] [image_difficulty]"""
        # Create a fake interaction-like object for compatibility
        channel_id = ctx.channel.id
        
        # Check if game already active
        if channel_id in self.active_games or channel_id in self.creating_games:
            await ctx.send("❌ A game is already active in this channel!")
            return
        
        self.creating_games.add(channel_id)
        
        # Validate parameters
        if mode not in ['image', 'audio']:
            self.creating_games.discard(channel_id)
            await ctx.send("❌ Mode must be 'image' or 'audio'")
            return
        
        if answer_type not in ['title', 'artist', 'difficulty']:
            self.creating_games.discard(channel_id)
            await ctx.send("❌ Answer type must be 'title', 'artist', or 'difficulty'")
            return
        
        rounds = max(1, min(50, rounds))
        time_limit = max(10, min(300, time_limit))
        snippet_length = max(5, min(30, snippet_length))
        
        if image_difficulty not in ['easy', 'medium', 'hard']:
            image_difficulty = 'easy'
        
        try:
            # Load songs
            all_songs = load_songs(difficulty="master")
            songs = all_songs
            
            if not songs:
                await ctx.send("❌ No songs found!")
                self.creating_games.discard(channel_id)
                return
            
            if len(songs) < rounds:
                rounds = len(songs)
            
            random.shuffle(songs)
            song_pool = songs[:rounds]
            
            # Filter by available media files
            if mode == 'image':
                song_pool = [s for s in song_pool if get_song_image_path(s)]
            elif mode == 'audio':
                song_pool = [s for s in song_pool if get_song_audio_path(s)]
            
            if not song_pool:
                await ctx.send(f"❌ No songs with {mode} files available!")
                self.creating_games.discard(channel_id)
                return
            
            if len(song_pool) < rounds:
                rounds = len(song_pool)
            
            config = {
                'mode': mode,
                'answer_type': answer_type,
                'time_limit': time_limit,
                'rounds': rounds,
                'snippet_length': snippet_length,
                'image_difficulty': image_difficulty,
                'song_pool': song_pool,
                'categories': None,  # Prefix command doesn't support filters
                'versions': None
            }
            
            game = GameSession(channel_id, ctx.author.id, config)
            self.active_games[channel_id] = game
            self.creating_games.discard(channel_id)
            
            difficulty_text = ""
            if mode == 'image':
                difficulty_labels = {'easy': 'Easy (full image)', 'medium': 'Medium (25%)', 'hard': 'Hard (10%)'}
                difficulty_text = f"\n**Image Difficulty:** {difficulty_labels.get(image_difficulty, image_difficulty)}"
            
            embed = discord.Embed(
                title="🎵 MaiMai Song Quiz Started!",
                description=f"**Mode:** {mode.title()}\n**Guess:** {answer_type.title()}\n**Rounds:** {rounds}\n**Time per round:** {time_limit}s{difficulty_text}",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Get ready! First round starting in 3 seconds...")
            
            await ctx.send(embed=embed)
            await asyncio.sleep(3)
            await self.start_round(ctx.channel)
            
        except Exception as e:
            await ctx.send(f"❌ Error starting game: {e}")
            self.creating_games.discard(channel_id)
            if channel_id in self.active_games:
                del self.active_games[channel_id]
    
    @commands.command(name="skip")
    async def prefix_skip(self, ctx):
        """Skip the current round. Usage: q>skip"""
        game = self.active_games.get(ctx.channel.id)
        
        if not game:
            await ctx.send("❌ No active game in this channel!")
            return
        
        if ctx.author.id != game.host_id:
            await ctx.send("❌ Only the host can skip rounds!")
            return
        
        await self.perform_skip(ctx.channel, game)
    
    @commands.command(name="stop")
    async def prefix_stop(self, ctx):
        """Stop the current game. Usage: q>stop"""
        game = self.active_games.get(ctx.channel.id)
        
        if not game:
            await ctx.send("❌ No active game in this channel!")
            return
        
        if ctx.author.id != game.host_id:
            await ctx.send("❌ Only the host can stop the game!")
            return
        
        if game.timeout_task:
            game.timeout_task.cancel()
        
        await self.end_game(ctx.channel, cancelled=True)
    
    @commands.command(name="lb", aliases=["leaderboard"])
    async def prefix_leaderboard(self, ctx):
        """Show current game leaderboard. Usage: q>lb or q>leaderboard"""
        game = self.active_games.get(ctx.channel.id)
        
        if not game:
            await ctx.send("❌ No active game in this channel!")
            return
        
        leaderboard = game.get_leaderboard()
        
        if not leaderboard:
            await ctx.send("No scores yet!")
            return
        
        embed = discord.Embed(
            title="🏆 Leaderboard",
            color=discord.Color.gold()
        )
        
        lb_text = ""
        for i, (user_id, score) in enumerate(leaderboard[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            lb_text += f"{medal} <@{user_id}>: {score} point(s)\n"
        
        embed.description = lb_text
        embed.set_footer(text=f"Round {game.current_round}/{game.total_rounds}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="qhelp", aliases=["qh"])
    async def prefix_help(self, ctx):
        """Show help message. Usage: q>qhelp"""
        embed = discord.Embed(
            title="🎵 MaiMai Quiz Bot Help",
            description="Guess songs from the MaiMai rhythm game!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Prefix Commands (q>)",
            value=(
                "• `q>quiz [mode] [answer_type] [rounds] [time_limit] [snippet_length]` - Start a quiz\n"
                "• `q>skip` - Skip current song (host only)\n"
                "• `q>stop` - Stop the game (host only)\n"
                "• `q>lb` - Show leaderboard\n"
                "• `q>qhelp` - Show this message\n"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Slash Commands",
            value=(
                "• `/quiz` - Start a quiz with full options\n"
                "• `/skip` - Skip current song\n"
                "• `/stop` - Stop the game\n"
                "• `/leaderboard` - Show scores\n"
                "• `/help` - Show help\n"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Game Modes",
            value="• `image` - Guess from cover art\n• `audio` - Guess from music clip",
            inline=True
        )
        
        embed.add_field(
            name="Answer Types",
            value="• `title` - Guess song title\n• `artist` - Guess artist\n• `difficulty` - Guess level",
            inline=True
        )
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(QuizCog(bot))
