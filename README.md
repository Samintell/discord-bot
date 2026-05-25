# MaiMai Quiz Bot

Discord bot for playing "Guess the Song" using MaiMai rhythm game data. Players are shown song cover images, hear audio snippets, or see animated chart pattern GIFs and guess the title, artist, or difficulty level.

## Setup

### Prerequisites

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/) installed and in PATH (required for audio mode)
- A Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications)

### Installation

```bash
pip install -r requirements.txt
```

For chart mode, install the Playwright browser:

```bash
playwright install chromium
```

### Configuration

1. Copy `.env.example` to `.env` and add your bot token:
   ```
   DISCORD_TOKEN=your_bot_token_here
   ```
   If you want a separate admin bot, add a second token:
   ```
   ADMIN_DISCORD_TOKEN=your_admin_bot_token_here
   ```
2. Enable **Message Content Intent** in the Discord Developer Portal under your bot's settings.

### Data Setup

1. Download/generate the song database:
   ```bash
   python scripts/convert_data.py
   ```
2. Download audio files:
   ```bash
   python scripts/download_audio.py
   ```
3. Download chart data (optional, for chart mode):
   ```bash
   python scripts/download_charts.py
   ```

Song cover images go in `images/`, audio files in `audio/`, and chart files in `charts/`.

### Running

```bash
python bot.py
```

For the optional admin bot:

```bash
python admin_bot.py
```

Commands sync automatically on startup. Use `q>sync` (bot owner only) to force-sync to the current server.

## Commands

### Slash Commands

| Command | Description |
|---------|-------------|
| `/quiz` | Start a quiz with full options (mode, answer type, rounds, filters, etc.) |
| `/skip` | Skip the current round (host only) |
| `/stop` | Stop the game (host only) |
| `/leaderboard` | Show current scores |
| `/filters` | Show available categories, versions, and regions |
| `/help` | Show help information |
| `/report_translation` | Report an incorrect English translation |
| `/report_audio` | Report an audio issue |

### Prefix Commands (`q>`)

| Command | Description |
|---------|-------------|
| `q>quiz [mode] [answer_type] [rounds] [time_limit] [snippet_length] [image_difficulty]` | Start a quiz |
| `q>skip` | Skip current round |
| `q>stop` | Stop the game |
| `q>lb` | Show leaderboard |
| `q>qhelp` | Show help |

### Admin Bot Commands (restricted)

These commands are hosted by the admin bot and will apply changes to the main bot.

| Command | Description |
|---------|-------------|
| `/translation add\|remove\|list` | Manage English translations |
| `/romaji add\|remove\|list` | Manage romaji overrides |
| `/alias add\|remove\|list` | Manage song aliases |
| `/reports translations\|audio\|clear` | View/clear user reports |
| `/refresh` | Re-run `scripts/convert_data.py` and reload song data |

## Game Modes

- **Image** - Guess from the song's cover art (easy/medium/hard crop sizes)
- **Audio** - Guess from a random audio snippet sent as a voice message
- **Chart** - Guess from an animated chart pattern GIF

## Answer Types

- **Title** - Guess the song title (accepts Japanese, romaji, English, and aliases)
- **Artist** - Guess the artist name
- **Difficulty** - Guess the chart level (exact numeric match, e.g. `13.7`)

## Filters

Quizzes can be filtered by:
- **Category** - `pops`, `vocaloid`, `touhou`, `game`, `maimai`, `ongeki`
- **Version** - `festival`, `buddies`, `prism`, etc.
- **Region** - `jp`, `intl`, `usa`
- **Level range** - Min/max chart level (e.g. 10 to 13.9)

## Project Structure

```
discord-bot/
├── bot.py                  # Main entry point
├── cogs/
│   ├── quiz.py             # Quiz game logic and commands
│   └── admin.py            # Admin commands
├── utils/
│   ├── constants.py        # Category, version, region mappings
│   ├── matcher.py          # Fuzzy answer matching
│   ├── song_loader.py      # Song database loading and filtering
│   ├── config_manager.py   # Config file CRUD (translations, romaji, aliases)
│   └── chart_renderer.py   # Chart GIF rendering via Playwright
├── config/
│   ├── known_translations.json
│   ├── romaji_overrides.json
│   └── aliases.json
├── scripts/
│   ├── convert_data.py         # Download and generate output.json
│   ├── download_audio.py       # Download audio files via yt-dlp
│   ├── download_charts.py      # Download chart data
│   ├── manual_audio_download.py  # Manual audio download helper
│   ├── replace_audio.py        # Audio replacement utility
│   ├── scrape_sekaipedia.py    # Sekaipedia translation scraper
│   └── update_remote.py        # Sync files to remote server via SCP
├── output.json             # Song database (generated)
├── images/                 # Cover art PNGs
├── audio/                  # Audio MP3 files
├── charts/                 # Simai chart files
└── new_songs/              # Staging area for new audio uploads
```

## Credits

- [Neskol](https://github.com/Neskol) for [Maichart-Converts](https://github.com/Neskol/Maichart-Converts): Charts
- [Non](https://x.com/non_otoge) and [Takerun](https://x.com/takerun_1224) for [mai-notes](https://mai-notes.com/): Chart Player
- [shedanial](https://github.com/shedaniel) for [tomomai](https://github.com/shedaniel/tomomai/tree/main): login flow
