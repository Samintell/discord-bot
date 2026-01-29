"""
Script to download audio files for MaiMai songs from YouTube using yt-dlp.
Searches for songs based on title and artist, downloads audio previews.
"""

import json
import os
from pathlib import Path
import yt_dlp
import time

# Configuration
AUDIO_DIR = Path("audio")
OUTPUT_JSON = Path("output.json")
AUDIO_FORMAT = "mp3"
AUDIO_QUALITY = "5"  # 0=best, 9=worst
PREVIEW_LENGTH = None  # None for full song, or set to seconds for preview
PREVIEW_START = 30   # Start position if using previews
TEST_LIMIT = None  # Set to None to download all, or number to test with limited songs
DEBUG = False  # Set to True for verbose output to debug 403 errors

# Create audio directory if it doesn't exist
AUDIO_DIR.mkdir(exist_ok=True)

def load_songs():
    """Load and filter songs from output.json (master difficulty only)."""
    with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
        songs = json.load(f)
    
    # Filter to master difficulty and deduplicate by song_id
    master_songs = {}
    for song in songs:
        if song.get('difficulty') == 'master':
            song_id = song['song_id']
            if song_id not in master_songs:
                master_songs[song_id] = song
    
    return list(master_songs.values())

def get_audio_filename(song):
    """Generate audio filename from song data."""
    # Use image filename as base, replace .png with .mp3
    image_name = song.get('image', '')
    if image_name:
        return image_name.replace('.png', '.mp3')
    else:
        # Fallback: use song_id
        return f"{song['song_id']}.mp3"

def search_youtube(query):
    """Search YouTube and return the first video URL."""
    # Check if cookies.txt exists
    cookies_file = Path("cookies.txt")
    
    ydl_opts = {
        'quiet': not DEBUG,
        'no_warnings': not DEBUG,
        'verbose': DEBUG,
        'extract_flat': True,
        'default_search': 'ytsearch1',  # Return only first result
    }
    
    # Use cookies file if it exists
    if cookies_file.exists():
        ydl_opts['cookiefile'] = str(cookies_file)
        if DEBUG:
            print(f"  🍪 Using cookies from: {cookies_file}")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if result and 'entries' in result and len(result['entries']) > 0:
                video_url = result['entries'][0]['url']
                video_title = result['entries'][0].get('title', 'Unknown')
                if DEBUG:
                    print(f"  🔗 Found: {video_title}")
                    print(f"  🔗 URL: {video_url}")
                return video_url
    except Exception as e:
        print(f"  ❌ Search error: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
    
    return None

def download_audio(url, output_path):
    """Download audio from YouTube URL."""
    # Check if cookies.txt exists
    cookies_file = Path("cookies.txt")
    
    if DEBUG:
        print(f"  📥 Attempting download from: {url}")
        print(f"  📂 Output path: {output_path}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path.with_suffix('')),  # Without extension
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': AUDIO_FORMAT,
            'preferredquality': AUDIO_QUALITY,
        }],
        'quiet': not DEBUG,
        'no_warnings': not DEBUG,
        'verbose': DEBUG,
        # Additional options for debugging 403 errors
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],  # Try multiple clients
            }
        },
    }
    
    # Use cookies file if it exists
    if cookies_file.exists():
        ydl_opts['cookiefile'] = str(cookies_file)
        if DEBUG:
            print(f"  🍪 Using cookies from: {cookies_file}")
    
    # Add trimming if preview length is specified
    if PREVIEW_LENGTH:
        ydl_opts['postprocessor_args'] = [
            '-ss', str(PREVIEW_START),
            '-t', str(PREVIEW_LENGTH),
        ]
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if DEBUG:
            print(f"  ✅ Download successful")
        return True
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        print(f"  ❌ Download error: {e}")
        if '403' in error_msg:
            print(f"  ⚠️  403 Forbidden - YouTube is blocking the request")
            print(f"  💡 Try: 1) Update yt-dlp: pip install -U yt-dlp")
            print(f"  💡      2) Use cookies: export cookies.txt from browser")
            print(f"  💡      3) Wait a while (rate limiting)")
        if DEBUG:
            import traceback
            traceback.print_exc()
        return False
    except Exception as e:
        print(f"  ❌ Download error: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
        return False

def main():
    print("🎵 MaiMai Audio Downloader")
    print("=" * 60)
    
    # Load songs
    print("\n📂 Loading songs from output.json...")
    songs = load_songs()
    print(f"✅ Found {len(songs)} unique master difficulty songs")
    
    # Track statistics
    downloaded = 0
    skipped = 0
    failed = 0
    failed_songs = []  # Track which songs failed
    
    # Download audio for each song
    songs_to_process = songs[:TEST_LIMIT] if TEST_LIMIT else songs
    total_songs = len(songs_to_process)
    
    for i, song in enumerate(songs_to_process, 1):
        title = song.get('title', 'Unknown')
        romaji = song.get('romaji', '')
        artist = song.get('artist', 'Unknown')
        
        # Display progress
        print(f"\n[{i}/{total_songs}] {romaji or title}")
        print(f"  Artist: {artist}")
        
        # Check if audio already exists
        audio_filename = get_audio_filename(song)
        audio_path = AUDIO_DIR / audio_filename
        
        if audio_path.exists():
            print(f"  ⏭️  Already exists: {audio_filename}")
            skipped += 1
            continue
        
        # Create search query (prefer original title for better YouTube results)
        search_query = f"{title} {artist}"
        print(f"  🔍 Searching: {search_query}")
        
        # Search YouTube
        video_url = search_youtube(search_query)
        
        if not video_url:
            print(f"  ❌ No results found")
            failed += 1
            failed_songs.append({"title": title, "romaji": romaji, "artist": artist, "reason": "No YouTube results"})
            continue
        
        print(f"  📥 Downloading...")
        
        # Download audio
        if download_audio(video_url, audio_path):
            print(f"  ✅ Saved: {audio_filename}")
            downloaded += 1
        else:
            print(f"  ❌ Failed to download")
            failed += 1
            failed_songs.append({"title": title, "romaji": romaji, "artist": artist, "reason": "Download error"})
        
        # Rate limiting to avoid YouTube throttling
        time.sleep(2)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"  ✅ Downloaded: {downloaded}")
    print(f"  ⏭️  Skipped (already exists): {skipped}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Total files in audio/: {len(list(AUDIO_DIR.glob('*.mp3')))}")
    
    # List failed songs
    if failed_songs:
        print("\n" + "=" * 60)
        print(f"❌ Failed Songs ({len(failed_songs)}):")
        print("=" * 60)
        for i, song in enumerate(failed_songs, 1):
            print(f"{i}. {song['romaji'] or song['title']}")
            print(f"   Artist: {song['artist']}")
            print(f"   Reason: {song['reason']}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Download interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
