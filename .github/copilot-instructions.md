# MaiMai Discord Song Quiz Bot

## Project Overview

Discord bot for playing "Guess the Song" using MaiMai rhythm game charts. Users are shown song cover images and guess the title, artist, or other attributes.

## Architecture & Data Flow

### Core Components
- **Game Engine**: Manages quiz sessions, scoring, and round progression
- **Song Database**: `output.json` contains 21,494+ song entries with metadata
- **Image Assets**: `images/` folder with 1,700+ PNG cover art files
- **Discord Interface**: Commands for starting games, submitting guesses, viewing scores

### Song Data Structure
Each song entry in `output.json`:
```json
{
  "song_id": "unique_identifier",      // Primary key, same for multiple difficulties
  "title": "日本語タイトル",             // Japanese title (Unicode)
  "romaji": "Romanized title",         // Latin alphabet version for guessing
  "artist": "Artist name",
  "category": "POPS＆アニメ",           // Genre categories
  "version": "maimai version",         // Game version it appeared in
  "type": "dx" | "std",                // Chart type
  "difficulty": "master",              // Chart difficulty level
  "level": 12.5,                       // Numeric difficulty rating
  "image": "filename.png"              // Corresponds to images/ folder
}
```

**Key Data Patterns:**
- Multiple difficulty entries share the same `song_id` and `image`
- Categories include: `POPS＆アニメ`, `niconico＆ボーカロイド`, `東方Project`, `ゲーム＆バラエティ`, `maimai`, etc.
- Image filenames may contain Unicode characters - handle with path encoding
- `romaji` field is primary for English matching; `title` is original Japanese

## Game Logic Design

### Game Modes & Configuration
- **Guess Type**: Image (show cover art) OR Audio (play song clip)
- **Answer Type**: Title OR Artist (configurable per session)
- **Time Limit**: Adjustable per session (e.g., 30s, 60s, 90s)
- **Multiplayer**: Multiple users compete simultaneously - first correct answer wins the point

### Typical Quiz Flow
1. Load song pool from `output.json` filtering:
   - **Only `difficulty: "master"`** entries (ignore other difficulties)
   - Optional: filter by `category` (e.g., `POPS＆アニメ`, `東方Project`)
   - Optional: filter by `version` (e.g., `FESTiVAL`, `BUDDiES`)
2. Deduplicate by `song_id` (since master-only filtering reduces duplicates)
3. Send cover image from `images/` OR audio clip as Discord embed
4. Start countdown timer (adjustable: 30-120 seconds)
5. Accept guesses from all participants until:
   - Someone answers correctly (first correct wins)
   - Timer expires (reveal answer, no points awarded)
6. Display: winner username, response time in seconds, correct answer
7. Update scores and proceed to next round

### Answer Matching Strategy
**Critical: Accept BOTH Japanese (`title`) and romaji (`romaji`) answers**
- **Partial matching required**: Use substring/fuzzy matching (e.g., `difflib.SequenceMatcher` with threshold ~0.8)
- Normalize all inputs: lowercase, strip punctuation, remove extra whitespace
- For artist mode: match against `artist` field with same partial logic
- Example matches:
  - Input: "kimi no shiranai" → Matches: "Kimi no shiranai monogatari"
  - Input: "君の知らない" → Matches: "君の知らない物語"
  - Input: "supercell" → Matches: "supercell「化物語」" (artist mode)

## Discord Bot Patterns

### Essential Libraries
- `discord.py` (or `py-cord`/`disnake`) for Discord API
- `Pillow` for image processing if creating composite images
- `asyncio` for concurrent game sessions per channel/server

### Command Structure
Typical commands to implement:
- `/quiz start [mode] [answer_type] [rounds] [time_limit] [category] [version]`
  - `mode`: `image` or `audio`
  - `answer_type`: `title` or `artist`
  - `rounds`: number of songs (default: 10)
  - `time_limit`: seconds per round (default: 60)
  - `category`: filter songs (optional, e.g., `POPS＆アニメ`)
  - `version`: filter by game version (optional, e.g., `FESTiVAL`)
- `/guess <answer>` - Submit guess (no command needed, listen to all messages in channel)
- `/skip` - Vote to skip current song (majority vote or host-only)
- `/leaderboard` - Show current session scores
- `/quiz stop` - End active session (host-only or majority vote)

### State Management
- Track active games per Discord channel (dict keyed by `channel.id`)
- Store per session:
  - Current song data (for answer validation)
  - Game config: mode (image/audio), answer_type (title/artist), time_limit
  - Remaining song pool (filtered master difficulty only)
  - Player scores (dict: `user_id` → points)
  - Round number, total rounds
  - Round start timestamp (for calculating response time)
  - Timeout task (asyncio.Task for timer)
- Clean up state when game ends or bot restarts

### Scoring System
- **1 point** for first correct answer per round
- **Only first person** to answer correctly gets the point
- Display response time: `{username} got it in {seconds:.2f}s!`
- No points awarded if timer expires before correct answer

## File Organization

When implementing the bot:
```
discord-bot/
├── bot.py                 # Main entry point, Discord client setup
├── cogs/
│   └── quiz.py           # Quiz commands and game logic
├── utils/
│   ├── song_loader.py    # Load/parse output.json
│   └── matcher.py        # Answer matching logic
├── config.py             # Bot token, settings
├── .env                  # Environment variables (DISCORD_TOKEN)
├── requirements.txt      # Dependencies
├── output.json           # Song database (existing)
└── images/               # Cover art (existing)
```

## Development Workflow

### Setup
1. Install Python 3.8+ and dependencies: `pip install discord.py python-dotenv`
2. Create Discord bot at https://discord.com/developers/applications
3. Store token in `.env`: `DISCORD_TOKEN=your_token_here`
4. Test data loading: verify `output.json` parses correctly with UTF-8 encoding

### Running Locally
```powershell
python bot.py
```

### Testing Without Discord
- Create unit tests for song loading, duplicate filtering, answer matching
- Mock Discord objects for command testing

## Common Pitfalls

1. **Unicode Handling**: Always open `output.json` with `encoding='utf-8'`
2. **Path Resolution**: Use `pathlib.Path` or `os.path.join` for cross-platform image paths
3. **Image File Mismatches**: Some `image` values may not have corresponding files - handle missing files gracefully
4. **Master Difficulty Only**: Filter `difficulty == "master"` early to avoid duplicates
5. **Concurrent Games**: Multiple channels can run games simultaneously - ensure proper state isolation
6. **Race Conditions**: Lock round state when processing guesses (first correct answer only)
7. **Partial Matching**: Balance fuzzy threshold - too low = false positives, too high = frustration
8. **Timer Cleanup**: Cancel `asyncio.Task` timers properly when round ends early
9. **Discord Rate Limits**: Don't send images too rapidly; use embeds efficiently
10. **Audio Files**: If implementing audio mode, ensure audio files exist (may need separate download/generation)

## Bot Token Security
- **Never commit** `.env` or hardcoded tokens to git
- Add to `.gitignore`: `.env`, `*.pyc`, `__pycache__/`, `.vscode/`
