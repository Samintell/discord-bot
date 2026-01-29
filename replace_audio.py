"""
Script to manually replace audio files for specific MaiMai songs.
Search for a song and provide a YouTube link to download/replace its audio.
"""

import json
import os
from pathlib import Path
import yt_dlp
import sys
import time

# Configuration
AUDIO_DIR = Path("audio")
OUTPUT_JSON = Path("output.json")
AUDIO_FORMAT = "mp3"
AUDIO_QUALITY = "5"  # 0=best, 9=worst

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
    image_name = song.get('image', '')
    if image_name:
        return image_name.replace('.png', '.mp3')
    else:
        return f"{song['song_id']}.mp3"

def search_songs(songs, query):
    """Search songs by title, romaji, or artist."""
    query_lower = query.lower()
    results = []
    
    for song in songs:
        title = song.get('title', '').lower()
        romaji = song.get('romaji', '').lower()
        artist = song.get('artist', '').lower()
        english = song.get('english', '').lower()
        
        if (query_lower in title or 
            query_lower in romaji or 
            query_lower in artist or
            query_lower in english):
            results.append(song)
    
    return results

def download_audio(url, output_path):
    """Download audio from YouTube URL."""
    cookies_file = Path("cookies.txt")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path.with_suffix('')),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': AUDIO_FORMAT,
            'preferredquality': AUDIO_QUALITY,
        }],
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
    }
    
    if cookies_file.exists():
        ydl_opts['cookiefile'] = str(cookies_file)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"  ❌ Download error: {e}")
        return False

def display_song(song, index=None):
    """Display song information."""
    prefix = f"[{index}] " if index is not None else ""
    title = song.get('title', 'Unknown')
    romaji = song.get('romaji', '')
    artist = song.get('artist', 'Unknown')
    audio_filename = get_audio_filename(song)
    audio_path = AUDIO_DIR / audio_filename
    has_audio = "✅" if audio_path.exists() else "❌"
    
    print(f"{prefix}{has_audio} {romaji or title}")
    if romaji and romaji != title:
        print(f"    JP: {title}")
    print(f"    Artist: {artist}")
    print(f"    File: {audio_filename}")

def main():
    print("🎵 MaiMai Audio Replacer")
    print("=" * 60)
    print("Search for songs and provide YouTube links to download/replace audio.")
    print("=" * 60)
    
    # Load songs
    print("\n📂 Loading songs...")
    songs = load_songs()
    print(f"✅ Loaded {len(songs)} songs")
    
    print("\nCommands:")
    print("  - Type a search query to find songs")
    print("  - Type 'missing' to list songs without audio")
    print("  - Type 'q' to quit")
    print()
    
    while True:
        try:
            query = input("\n🔍 Search (or 'q' to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break
        
        if not query:
            continue
        
        if query.lower() == 'q':
            print("👋 Goodbye!")
            break
        
        # Special command: list missing audio
        if query.lower() == 'missing':
            missing = [s for s in songs if not (AUDIO_DIR / get_audio_filename(s)).exists()]
            print(f"\n📋 Songs without audio ({len(missing)}):")
            for i, song in enumerate(missing[:20], 1):
                display_song(song, i)
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more")
            continue
        
        # Search for songs
        results = search_songs(songs, query)
        
        if not results:
            print("  No songs found matching your query.")
            continue
        
        print(f"\n📋 Found {len(results)} song(s):")
        display_limit = min(len(results), 20)
        for i, song in enumerate(results[:display_limit], 1):
            display_song(song, i)
        
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more (refine your search)")
        
        # Ask which song to update
        while True:
            try:
                choice = input("\n🎯 Enter song number to replace audio (or 'b' to go back): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye!")
                return
            
            if choice.lower() == 'b' or choice.lower() == 'back':
                break
            
            try:
                song_index = int(choice) - 1
                if 0 <= song_index < len(results[:display_limit]):
                    selected_song = results[song_index]
                    break
                else:
                    print("  ⚠️ Invalid number. Try again.")
            except ValueError:
                print("  ⚠️ Please enter a number or 'b' to go back.")
        else:
            continue
        
        # Show selected song details
        print("\n" + "=" * 60)
        print("Selected song:")
        display_song(selected_song)
        print("=" * 60)
        
        audio_filename = get_audio_filename(selected_song)
        audio_path = AUDIO_DIR / audio_filename
        
        if audio_path.exists():
            print(f"⚠️  Audio file already exists: {audio_filename}")
            confirm = input("   Replace it? (y/n): ").strip().lower()
            if confirm != 'y':
                print("   Cancelled.")
                continue
            # Backup old file
            backup_path = audio_path.with_suffix('.mp3.bak')
            try:
                audio_path.rename(backup_path)
                print(f"   📦 Backed up to: {backup_path.name}")
            except Exception as e:
                print(f"   ⚠️ Could not backup: {e}")
        
        # Get YouTube URL
        try:
            url = input("\n🔗 Enter YouTube URL: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break
        
        if not url:
            print("  ⚠️ No URL provided. Cancelled.")
            continue
        
        if not ('youtube.com' in url or 'youtu.be' in url):
            print("  ⚠️ This doesn't look like a YouTube URL.")
            continue
        
        # Download
        print(f"\n📥 Downloading...")
        
        # Track files before download
        files_before = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
        
        if download_audio(url, audio_path):
            time.sleep(0.5)
            
            if audio_path.exists():
                print(f"\n✅ Successfully saved: {audio_filename}")
                # Remove backup if exists
                backup_path = audio_path.with_suffix('.mp3.bak')
                if backup_path.exists():
                    try:
                        backup_path.unlink()
                        print(f"   🗑️ Removed backup file")
                    except:
                        pass
            else:
                # Try to find the downloaded file
                files_after = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
                new_files = [f for f, mtime in files_after.items() 
                           if f not in files_before or mtime > files_before.get(f, 0)]
                
                if new_files:
                    new_file = new_files[0]
                    print(f"  🔄 Renaming '{new_file.name}' to '{audio_filename}'")
                    try:
                        new_file.rename(audio_path)
                        print(f"\n✅ Successfully saved: {audio_filename}")
                    except Exception as e:
                        print(f"  ⚠️ Rename failed: {e}")
                        print(f"  File saved as: {new_file.name}")
                else:
                    print(f"  ⚠️ Download completed but file not found.")
                    # Restore backup if available
                    backup_path = audio_path.with_suffix('.mp3.bak')
                    if backup_path.exists():
                        try:
                            backup_path.rename(audio_path)
                            print(f"  🔄 Restored backup")
                        except:
                            pass
        else:
            print(f"\n❌ Download failed.")
            # Restore backup if available
            backup_path = audio_path.with_suffix('.mp3.bak')
            if backup_path.exists():
                try:
                    backup_path.rename(audio_path)
                    print(f"  🔄 Restored backup")
                except:
                    pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
