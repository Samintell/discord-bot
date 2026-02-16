# MaiMai Discord Song Quiz Bot

## Project Overview

Discord bot for playing "Guess the Song" using MaiMai rhythm game data. Users are shown song cover images, hear audio snippets, or see animated chart pattern GIFs and guess the title, artist, or difficulty level.

## Architecture & Data Flow

### Core Components
- **Game Engine** (`cogs/quiz.py`): Manages quiz sessions, scoring, and round progression using `GameSession` class
- **Song Database**: `output.json` contains 21,494+ song entries with metadata
- **Image Assets**: `images/` folder with 1,700+ PNG cover art files
- **Audio Assets**: `audio/` folder with MP3 files (same base name as images)
- **Chart Assets**: `charts/` folder with processed simai chart files (one per song per difficulty)
- **Discord Interface**: Slash commands (`/quiz`, `/skip`, `/stop`, etc.) and prefix commands (`q>quiz`, `q>skip`, etc.)

### Song Data Structure
Each song entry in `output.json`:
```json
{
  "song_id": "unique_identifier",      // Primary key, same for multiple difficulties
  "title": "日本語タイトル",             // Japanese title (Unicode)
  "romaji": "Romanized title",         // Latin alphabet version for guessing
  "english": "English translation",    // Optional English title
  "artist": "Artist name",
  "category": "POPS＆アニメ",           // Genre categories
  "version": "maimai version",         // Game version it appeared in
  "type": "dx" | "std",                // Chart type
  "difficulty": "master",              // Chart difficulty level
  "level": 12.5,                       // Numeric difficulty rating
  "image": "filename.png",             // Corresponds to images/ folder
  "regions": ["jp", "intl", "usa"]     // Available regions array
}
```

**Key Data Patterns:**
- Multiple difficulty entries share the same `song_id` and `image`
- Categories: `POPS＆アニメ`, `niconico＆ボーカロイド`, `東方Project`, `ゲーム＆バラエティ`, `maimai`, `オンゲキ＆CHUNITHM`
- Image filenames may contain Unicode characters - handle with path encoding
- Audio files use same base name as images with `.mp3` extension
- Accepts `master` and `remaster` difficulties for filtering

## Game Logic Design

### Game Modes & Configuration
- **Mode**: `image` (show cover art), `audio` (play song snippet as voice message), OR `chart` (show animated chart GIF)
- **Answer Type**: `title`, `artist`, OR `difficulty` (configurable per session)
- **Time Limit**: 10-300 seconds per round (default: 20s)
- **Rounds**: 1-50 rounds per game (default: 10)
- **Audio Snippet Length**: 5-30 seconds (default: 10s)
- **Image Difficulty**: `easy` (full image), `medium` (25% crop), `hard` (10% crop)
- **Filtering**: By category, version, and/or region (comma-separated lists)
- **Region**: `any` (all songs), `jp` (Japan), `intl` (International), `usa` (USA)
- **Multiplayer**: Multiple users compete simultaneously - first correct answer wins the point

### Quiz Flow Implementation
1. `/quiz` command triggers `quiz_start()` in `QuizCog`
2. Load song pool from `output.json` via `song_loader.load_songs()`:
   - Filter by `difficulty: "master"` or `"remaster"`
   - Optional: filter by `category`, `version`, and/or `region`
   - Deduplicate by `song_id` (keeping highest level)
3. Create `GameSession` object with config and song pool
4. For each round (`start_round()`):
   - Pop next song from pool
   - Send embed with Skip button (`SkipButton` view)
   - For image mode: crop image based on difficulty setting
   - For audio mode: create OGG Opus snippet via ffmpeg, send as Discord voice message
   - For chart mode: render simai chart GIF via Playwright + mai-notes.com player
5. Listen for guesses via `on_message()` listener
6. Use `check_answer()` from `utils/matcher.py` for fuzzy matching
7. First correct answer wins point; display response time and answer
8. Timeout handled by `asyncio.Task` (`round_timeout()`)
9. End game shows leaderboard and "Play Again" button (`PlayAgainButton` view)

### Answer Matching Strategy (`utils/matcher.py`)
**Accepts Japanese (`title`), romaji (`romaji`), AND English (`english`) answers**
- **Fuzzy matching**: Uses `difflib.SequenceMatcher` with dynamic thresholds
- **Length-based minimums**: Requires 25-40% of target length depending on title length
- **Substring matching**: Direct substring matches are accepted
- **Start matching**: For long titles, typing the beginning is accepted
- **Normalization**: lowercase, strip punctuation, remove extra whitespace
- **Difficulty matching**: Exact numeric match required (e.g., "13.7")

**Threshold adjustments by target length:**
- < 10 chars: require 40% of length, threshold 0.8
- 10-20 chars: require 35%, threshold 0.75
- 20-40 chars: require 30%, threshold 0.7
- 40+ chars: require 25%, threshold 0.65

## Discord Bot Implementation

### Dependencies (`requirements.txt`)
```
discord.py>=2.0.0
python-dotenv>=0.19.0
Pillow>=9.0.0
yt-dlp>=2023.0.0
requests>=2.28.0
playwright>=1.40.0
imageio>=2.31.0
```

**External requirement**: `ffmpeg` and `ffprobe` must be installed for audio snippet creation
**External requirement**: Playwright Chromium browser required for chart mode: `playwright install chromium`

### Command Structure

#### Slash Commands (Primary)
- `/quiz` - Start quiz with full options:
  - `mode`: Image, Audio, or Chart
  - `answer_type`: Title, Artist, or Difficulty Level
  - `rounds`: 1-50 (default: 10)
  - `time_limit`: 10-300 seconds (default: 20)
  - `snippet_length`: 5-30 seconds (default: 10, audio mode only)
  - `image_difficulty`: Easy/Medium/Hard (image mode only)
  - `categories`: Comma-separated filter (e.g., "pops,touhou")
  - `versions`: Comma-separated filter (e.g., "festival,buddies")
  - `region`: Any, Japan, International, or USA
- `/skip` - Skip current round (host only)
- `/stop` - End game (host only)
- `/leaderboard` - Show current scores
- `/filters` - Show available categories, versions, and regions
- `/help` - Show help information
- `/report_translation` - Report incorrect English translation
- `/report_audio` - Report audio issues

#### Prefix Commands (`q>`)
- `q>quiz [mode] [answer_type] [rounds] [time_limit] [snippet_length] [image_difficulty]`
- `q>skip` - Skip current round
- `q>stop` - Stop game
- `q>lb` or `q>leaderboard` - Show scores
- `q>qhelp` - Show help

### State Management (`GameSession` class)
```python
class GameSession:
    channel_id: int
    host_id: int
    mode: str  # 'image', 'audio', or 'chart'
    answer_type: str  # 'title', 'artist', or 'difficulty'
    time_limit: int
    total_rounds: int
    snippet_length: int
    image_difficulty: str  # 'easy', 'medium', 'hard'
    current_round: int
    song_pool: List[dict]
    current_song: Optional[dict]
    scores: Dict[int, int]  # user_id -> score
    round_start_time: Optional[datetime]
    timeout_task: Optional[asyncio.Task]
    answered: bool
    original_config: dict  # For replay functionality
```

- Active games tracked in `QuizCog.active_games: Dict[channel_id, GameSession]`
- Game creation tracked in `QuizCog.creating_games: set` to prevent duplicates
- Each channel can have one active game; multiple channels can run simultaneously

### UI Components
- **SkipButton**: `discord.ui.View` with skip button, host-only access
- **PlayAgainButton**: Appears after game ends, restarts with same config

### Audio Handling
- Audio snippets created via `create_audio_snippet()` using ffmpeg
- Converts to OGG Opus format with loudnorm filter for consistent volume
- Sent as Discord voice messages using low-level API (`send_voice_message()`)
- Temporary snippets stored in `audio/snippets/` and cleaned up after sending

### Image Handling
- `crop_image_for_difficulty()` uses Pillow to crop images:
  - `easy`: Full image
  - `medium`: Random 50% x 50% crop (25% of area)
  - `hard`: Random ~31.6% x ~31.6% crop (10% of area)

### Chart Handling
- Chart data downloaded from Maichart-Converts GitHub repo via `download_charts.py`
- Processed simai chart files stored in `charts/` folder as `{song_id}_{difficulty}.txt`
- `charts/chart_index.json` maps song_ids to available chart file paths
- GIF rendering via Playwright + mai-notes.com player (`utils/chart_renderer.py`)
- `ChartRenderer` class manages browser lifecycle (lazy init, reused across rounds)
- GIFs are generated on-demand: 5-8 second excerpts at 10fps, 500x500px canvas
- Temporary GIF files in `charts/gif_cache/` cleaned up after sending to Discord
- `get_song_chart_path()` in `song_loader.py` resolves chart file paths (falls back to remaster if master not found)

## File Organization

```
discord-bot/
├── bot.py                 # Main entry, Discord client setup, command prefix q>
├── cogs/
│   └── quiz.py           # QuizCog with all game logic and commands
├── utils/
│   ├── constants.py      # CATEGORIES, VERSIONS, and mapping dicts
│   ├── matcher.py        # check_answer(), fuzzy_match(), normalize_string()
│   ├── song_loader.py    # load_songs(), get_song_image_path(), get_song_audio_path(), get_song_chart_path()
│   └── chart_renderer.py # ChartRenderer class for GIF generation via Playwright
├── .env                  # DISCORD_TOKEN=your_token_here
├── .env.example          # Template for .env
├── requirements.txt      # Python dependencies
├── output.json           # Song database
├── images/               # Cover art PNG files
├── audio/                # Full audio MP3 files
│   └── snippets/         # Temporary audio snippets (auto-cleaned)
├── charts/               # Processed simai chart files
│   ├── chart_index.json  # Maps song_id -> chart file paths
│   ├── gif_cache/        # Temporary chart GIFs (auto-cleaned)
│   └── *.txt             # Individual simai chart files ({song_id}_{difficulty}.txt)
├── new_songs/            # New songs to be added
├── convert_data.py       # Data conversion utility
├── download_audio.py     # Audio download script using yt-dlp
├── download_charts.py    # Chart download/processing from Maichart-Converts repo
├── manual_audio_download.py  # Manual audio download helper
├── replace_audio.py      # Audio replacement utility
├── yt-dlp.conf           # yt-dlp configuration
├── data.json             # Additional data file
└── translation_submissions.json  # User-submitted translation corrections (auto-generated)
```

## Constants (`utils/constants.py`)

### Categories
```python
CATEGORIES = {
    "POPS＆アニメ": "pops",
    "niconico＆ボーカロイド": "vocaloid", 
    "東方Project": "touhou",
    "ゲーム＆バラエティ": "game",
    "maimai": "maimai",
    "オンゲキ＆CHUNITHM": "ongeki"
}
```

### Versions (subset)
```python
VERSIONS = {
    "FESTiVAL": "festival",
    "FESTiVAL PLUS": "festival plus",
    "BUDDiES": "buddies",
    "BUDDiES PLUS": "buddies plus",
    "PRiSM": "prism",
    "PRiSM PLUS": "prism plus",
    "CiRCLE": "circle",
    # ... and many more
}
```

### Regions
```python
REGIONS = {
    "Japan": "jp",
    "International": "intl",
    "USA": "usa"
}
```

Both English (lowercase) and Japanese names are accepted for filtering via `CATEGORY_MAPPING`, `VERSION_MAPPING`, and `REGION_MAPPING`.

## Development Workflow

### Setup
1. Install Python 3.8+ and dependencies: `pip install -r requirements.txt`
2. Install ffmpeg (required for audio mode)
3. Install Playwright Chromium (required for chart mode): `playwright install chromium`
4. Create Discord bot at https://discord.com/developers/applications
5. Copy `.env.example` to `.env` and add your token: `DISCORD_TOKEN=your_token_here`
6. Enable Message Content Intent in Discord Developer Portal
7. Download chart data: `python download_charts.py`

### Running
```powershell
python bot.py
```

### Syncing Commands
- Commands sync automatically on startup
- Use `q>sync` (bot owner only) to force sync to current server

## Common Pitfalls

1. **Unicode Handling**: Always open files with `encoding='utf-8'`
2. **Path Resolution**: Use `pathlib.Path` for cross-platform paths (see `PROJECT_ROOT` in song_loader.py)
3. **Missing Media Files**: `get_song_image_path()`, `get_song_audio_path()`, and `get_song_chart_path()` return `None` if file missing
4. **Master/Remaster Filter**: Both difficulties accepted, deduplication keeps highest level
5. **Concurrent Games**: One game per channel; `creating_games` set prevents race conditions
6. **Race Conditions**: `game.answered` flag ensures only first correct answer scores
7. **Fuzzy Matching**: Dynamic thresholds based on target length balance accuracy vs usability
8. **Timer Cleanup**: `asyncio.Task.cancel()` called when round ends early
9. **Audio Mode Requirements**: ffmpeg/ffprobe must be in PATH for snippet creation
10. **Voice Message API**: Uses low-level Discord API with IS_VOICE_MESSAGE flag (8192)
11. **Interaction Timeouts**: Respond to interactions immediately, then perform async work
12. **Chart Mode Dependencies**: Requires Playwright + Chromium browser; `ChartRenderer` lazy-initialized on first chart quiz
13. **Chart GIF Latency**: GIF generation takes ~7-14 seconds; chart is rendered during round setup

## Bot Token Security
- **Never commit** `.env` or hardcoded tokens to git
- `.gitignore` includes: `.env`, `*.pyc`, `__pycache__/`, `.vscode/`, `audio/snippets/`
