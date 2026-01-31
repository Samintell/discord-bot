"""
Script to manually add audio files for MaiMai songs with missing audio.
Allows user to input YouTube links for each song that's missing audio.
"""

import json
import os
from pathlib import Path
import yt_dlp
import sys
import argparse

# Configuration
AUDIO_DIR = Path("audio")
NEW_SONGS_DIR = Path("new_songs")
OUTPUT_JSON = Path("output.json")
AUDIO_FORMAT = "mp3"
AUDIO_QUALITY = "5"  # 0=best, 9=worst
PROGRESS_FILE = Path("manual_download_progress.json")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="MaiMai Manual Audio Downloader")
    parser.add_argument('--replace', '-r', action='store_true',
                        help='Replace mode: search for and replace existing audio files')
    parser.add_argument('--search', '-s', type=str, default=None,
                        help='Search for a specific song by title/romaji (use with --replace)')
    return parser.parse_args()

# Create directories if they don't exist
AUDIO_DIR.mkdir(exist_ok=True)
NEW_SONGS_DIR.mkdir(exist_ok=True)

def copy_to_new_songs(audio_path: Path):
    """Copy an audio file to the new_songs directory."""
    import shutil
    try:
        dest_path = NEW_SONGS_DIR / audio_path.name
        shutil.copy2(audio_path, dest_path)
        print(f"  📋 Copied to new_songs/: {audio_path.name}")
        return True
    except Exception as e:
        print(f"  ⚠️  Failed to copy to new_songs/: {e}")
        return False

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

def find_missing_audio(songs):
    """Find songs that don't have corresponding audio files."""
    missing = []
    for song in songs:
        audio_filename = get_audio_filename(song)
        audio_path = AUDIO_DIR / audio_filename
        
        if not audio_path.exists():
            missing.append(song)
    
    return missing

def search_songs(songs, query):
    """Search songs by title, romaji, or artist."""
    query_lower = query.lower()
    results = []
    
    for song in songs:
        title = song.get('title', '').lower()
        romaji = song.get('romaji', '').lower()
        artist = song.get('artist', '').lower()
        
        if query_lower in title or query_lower in romaji or query_lower in artist:
            results.append(song)
    
    return results

def find_songs_with_audio(songs):
    """Find songs that have audio files (for replace mode)."""
    with_audio = []
    for song in songs:
        audio_filename = get_audio_filename(song)
        audio_path = AUDIO_DIR / audio_filename
        
        if audio_path.exists():
            with_audio.append(song)
    
    return with_audio

def download_audio(url, output_path):
    """Download audio from YouTube URL."""
    # Check if cookies.txt exists
    cookies_file = Path("cookies.txt")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path.with_suffix('')),  # Without extension
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': AUDIO_FORMAT,
            'preferredquality': AUDIO_QUALITY,
        }],
        'quiet': False,  # Show download progress
        'no_warnings': False,
        'noplaylist': True,  # Download only the video, not playlist
        # Additional options for better compatibility
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
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"  ❌ Download error: {e}")
        return False

def load_progress():
    """Load progress from previous session."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"skipped": [], "completed": []}
    return {"skipped": [], "completed": []}

def save_progress(progress):
    """Save progress to file."""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

def get_user_input(prompt):
    """Get user input with proper encoding handling."""
    print(prompt, end='', flush=True)
    try:
        return input().strip()
    except EOFError:
        return None
    except KeyboardInterrupt:
        raise

def replace_mode(songs, search_query=None):
    """Replace mode: search for and replace existing audio files."""
    print("\n🔄 REPLACE MODE")
    print("=" * 60)
    print("Search for songs to replace their audio files.")
    print("=" * 60)
    
    while True:
        # Get search query
        if search_query:
            query = search_query
            search_query = None  # Only use command-line search once
        else:
            query = get_user_input("\n🔍 Search for song (or 'q' to quit): ")
        
        if query is None or query.lower() == 'q':
            print("\n👋 Exiting replace mode...")
            return
        
        if not query:
            print("  ⚠️  Please enter a search term")
            continue
        
        # Search for matching songs
        results = search_songs(songs, query)
        
        if not results:
            print(f"  ❌ No songs found matching '{query}'")
            continue
        
        # Show results
        print(f"\n📋 Found {len(results)} matching song(s):")
        for i, song in enumerate(results[:20], 1):  # Limit to 20 results
            title = song.get('title', 'Unknown')
            romaji = song.get('romaji', '')
            artist = song.get('artist', 'Unknown')
            audio_filename = get_audio_filename(song)
            audio_path = AUDIO_DIR / audio_filename
            has_audio = "✅" if audio_path.exists() else "❌"
            
            display_title = romaji if romaji else title
            print(f"  {i}. [{has_audio}] {display_title} - {artist}")
        
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more results")
        
        # Select song to replace
        selection = get_user_input("\n🎯 Enter number to select (or 'b' to go back): ")
        
        if selection is None or selection.lower() == 'b' or selection.lower() == 'q':
            continue
        
        try:
            idx = int(selection) - 1
            if idx < 0 or idx >= len(results):
                print("  ⚠️  Invalid selection")
                continue
        except ValueError:
            print("  ⚠️  Please enter a valid number")
            continue
        
        # Selected song
        song = results[idx]
        title = song.get('title', 'Unknown')
        romaji = song.get('romaji', '')
        artist = song.get('artist', 'Unknown')
        audio_filename = get_audio_filename(song)
        audio_path = AUDIO_DIR / audio_filename
        
        print(f"\n{'=' * 60}")
        print(f"Selected Song:")
        print(f"  Title (JP):  {title}")
        if romaji:
            print(f"  Title (Rom): {romaji}")
        print(f"  Artist:      {artist}")
        print(f"  Filename:    {audio_filename}")
        print(f"  Has Audio:   {'Yes' if audio_path.exists() else 'No'}")
        print(f"{'=' * 60}")
        
        # Get YouTube URL
        url = get_user_input("\n🔗 Enter YouTube URL (or 'b' to go back): ")
        
        if url is None or url.lower() == 'b':
            continue
        
        if not url:
            print("  ⚠️  No URL provided")
            continue
        
        if not ('youtube.com' in url or 'youtu.be' in url):
            print("  ⚠️  This doesn't look like a YouTube URL.")
            continue
        
        # Delete existing file if it exists
        if audio_path.exists():
            confirm = get_user_input(f"  ⚠️  This will replace the existing file. Continue? (y/n): ")
            if confirm is None or confirm.lower() != 'y':
                print("  ⏭️  Cancelled")
                continue
            
            try:
                audio_path.unlink()
                print(f"  🗑️  Deleted existing file: {audio_filename}")
            except Exception as e:
                print(f"  ❌ Failed to delete existing file: {e}")
                continue
        
        # Download new audio
        print(f"  📥 Downloading from: {url}")
        
        # Get list of mp3 files before download
        files_before = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
        
        if download_audio(url, audio_path):
            import time
            time.sleep(0.5)
            
            if audio_path.exists():
                print(f"  ✅ Successfully saved: {audio_filename}")
                copy_to_new_songs(audio_path)
            else:
                # Check for new files (yt-dlp may have sanitized the filename)
                files_after = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
                new_files = [f for f, mtime in files_after.items() 
                            if f not in files_before or mtime > files_before.get(f, 0)]
                
                if new_files:
                    new_file = new_files[0]
                    print(f"  🔄 Renaming '{new_file.name}' to '{audio_filename}'")
                    try:
                        new_file.rename(audio_path)
                        print(f"  ✅ Successfully saved: {audio_filename}")
                        copy_to_new_songs(audio_path)
                    except Exception as e:
                        print(f"  ⚠️  Rename failed: {e}")
                        print(f"  ✅ File saved as: {new_file.name}")
                        copy_to_new_songs(new_file)
                else:
                    print(f"  ⚠️  Download completed but file not found")
        else:
            print(f"  ❌ Download failed")


def main():
    args = parse_args()
    
    print("🎵 MaiMai Manual Audio Downloader")
    print("=" * 60)
    
    # Load songs
    print("\n📂 Loading songs from output.json...")
    songs = load_songs()
    print(f"✅ Found {len(songs)} unique master difficulty songs")
    
    # Check for replace mode
    if args.replace:
        replace_mode(songs, args.search)
        return
    
    print("This script allows you to manually provide YouTube links")
    print("for songs that don't have audio files yet.")
    print("\nTip: Use --replace or -r flag to replace existing audio files")
    print("=" * 60)
    
    # Find missing audio
    print("\n🔍 Checking for missing audio files...")
    missing_songs = find_missing_audio(songs)
    print(f"❌ Found {len(missing_songs)} songs without audio files")
    
    if not missing_songs:
        print("\n🎉 All songs have audio files!")
        return
    
    # Load progress from previous session
    progress = load_progress()
    
    # Filter out already processed songs
    processed_ids = set(progress.get("skipped", []) + progress.get("completed", []))
    remaining_songs = [s for s in missing_songs if s["song_id"] not in processed_ids]
    
    if len(remaining_songs) < len(missing_songs):
        print(f"📋 Resuming from previous session...")
        print(f"   Already processed: {len(missing_songs) - len(remaining_songs)}")
        print(f"   Remaining: {len(remaining_songs)}")
    
    if not remaining_songs:
        print("\n✅ All missing songs have been processed!")
        print(f"   Completed: {len(progress['completed'])}")
        print(f"   Skipped: {len(progress['skipped'])}")
        return
    
    # Statistics
    downloaded = 0
    skipped = 0
    failed = 0
    
    print("\n" + "=" * 60)
    print("Commands:")
    print("  - Enter YouTube URL to download")
    print("  - Enter 's' to skip this song")
    print("  - Enter 'q' to quit")
    print("  - Enter 'list' to see first 10 remaining songs")
    print("=" * 60)
    
    try:
        for i, song in enumerate(remaining_songs, 1):
            title = song.get('title', 'Unknown')
            romaji = song.get('romaji', '')
            artist = song.get('artist', 'Unknown')
            song_id = song.get('song_id')
            audio_filename = get_audio_filename(song)
            
            print(f"\n{'=' * 60}")
            print(f"[{i}/{len(remaining_songs)}] Song Information:")
            print(f"  Title (JP):  {title}")
            if romaji:
                print(f"  Title (Rom): {romaji}")
            print(f"  Artist:      {artist}")
            print(f"  Filename:    {audio_filename}")
            print(f"{'=' * 60}")
            
            while True:
                user_input = get_user_input("\n🔗 Enter YouTube URL (or 's' to skip, 'q' to quit, 'list' to preview): ")
                
                if user_input is None or user_input.lower() == 'q':
                    print("\n👋 Quitting...")
                    save_progress(progress)
                    print(f"\n📊 Session Summary:")
                    print(f"  ✅ Downloaded: {downloaded}")
                    print(f"  ⏭️  Skipped: {skipped}")
                    print(f"  ❌ Failed: {failed}")
                    return
                
                if user_input.lower() == 's':
                    print("  ⏭️  Skipped")
                    skipped += 1
                    progress["skipped"].append(song_id)
                    save_progress(progress)
                    break
                
                if user_input.lower() == 'list':
                    print("\n📋 Next 10 songs:")
                    for j in range(i, min(i + 10, len(remaining_songs) + 1)):
                        if j <= len(remaining_songs):
                            s = remaining_songs[j-1]
                            print(f"  {j}. {s.get('romaji') or s.get('title')} - {s.get('artist')}")
                    continue
                
                if not user_input:
                    print("  ⚠️  Please enter a valid URL or command")
                    continue
                
                # Validate URL format
                if not ('youtube.com' in user_input or 'youtu.be' in user_input):
                    print("  ⚠️  This doesn't look like a YouTube URL. Try again.")
                    continue
                
                # Try to download
                audio_path = AUDIO_DIR / audio_filename
                print(f"  📥 Downloading from: {user_input}")
                
                # Get list of mp3 files before download (with modification times)
                files_before = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
                
                if download_audio(user_input, audio_path):
                    # Small delay to ensure file is written
                    import time
                    time.sleep(0.5)
                    
                    # Check if expected file exists
                    if audio_path.exists():
                        print(f"  ✅ Successfully saved: {audio_filename}")
                        copy_to_new_songs(audio_path)
                        downloaded += 1
                        progress["completed"].append(song_id)
                        save_progress(progress)
                        break
                    else:
                        # Check for new or modified files (yt-dlp may have sanitized the filename)
                        files_after = {f: f.stat().st_mtime for f in AUDIO_DIR.glob('*.mp3')}
                        
                        # Find new files or files with updated modification time
                        new_files = []
                        for f, mtime in files_after.items():
                            if f not in files_before or mtime > files_before.get(f, 0):
                                new_files.append(f)
                        
                        if new_files:
                            # Rename the new file to expected filename
                            new_file = new_files[0]
                            print(f"  🔄 Renaming '{new_file.name}' to '{audio_filename}'")
                            try:
                                new_file.rename(audio_path)
                                print(f"  ✅ Successfully saved: {audio_filename}")
                                copy_to_new_songs(audio_path)
                                downloaded += 1
                                progress["completed"].append(song_id)
                                save_progress(progress)
                                break
                            except Exception as e:
                                print(f"  ⚠️  Rename failed: {e}")
                                print(f"  ✅ File saved as: {new_file.name}")
                                copy_to_new_songs(new_file)
                                downloaded += 1
                                progress["completed"].append(song_id)
                                save_progress(progress)
                                break
                        else:
                            # Try searching by base name pattern (without extension issues)
                            base_name = audio_filename.replace('.mp3', '').replace('.', '')
                            matching_files = [f for f in AUDIO_DIR.glob('*.mp3') 
                                            if base_name[:5].lower() in f.name.lower()]
                            if matching_files:
                                # Get most recently modified
                                newest = max(matching_files, key=lambda f: f.stat().st_mtime)
                                print(f"  🔄 Found matching file: '{newest.name}'")
                                try:
                                    newest.rename(audio_path)
                                    print(f"  ✅ Successfully saved: {audio_filename}")
                                    copy_to_new_songs(audio_path)
                                    downloaded += 1
                                    progress["completed"].append(song_id)
                                    save_progress(progress)
                                    break
                                except Exception as e:
                                    print(f"  ⚠️  Rename failed: {e}")
                                    print(f"  ✅ File saved as: {newest.name}")
                                    copy_to_new_songs(newest)
                                    downloaded += 1
                                    progress["completed"].append(song_id)
                                    save_progress(progress)
                                    break
                            else:
                                print(f"  ⚠️  Download completed but file not found. Retrying...")
                else:
                    print(f"  ❌ Download failed. Try a different URL or skip.")
                    retry = get_user_input("  Retry with different URL? (y/n): ")
                    if retry and retry.lower() != 'y':
                        print("  ⏭️  Skipping this song")
                        skipped += 1
                        progress["skipped"].append(song_id)
                        save_progress(progress)
                        break
        
        # Final summary
        print("\n" + "=" * 60)
        print("🎉 All songs processed!")
        print("=" * 60)
        print("📊 Final Summary:")
        print(f"  ✅ Downloaded: {downloaded}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ❌ Failed: {failed}")
        print(f"  📁 Total audio files: {len(list(AUDIO_DIR.glob('*.mp3')))}")
        
        # Clean up progress file if everything is done
        if not skipped and not failed:
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
                print("\n✨ Progress file cleaned up")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        save_progress(progress)
        print(f"\n📊 Session Summary:")
        print(f"  ✅ Downloaded: {downloaded}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ❌ Failed: {failed}")
        print("\n💾 Progress saved! Run the script again to continue.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        save_progress(progress)
        raise

if __name__ == "__main__":
    main()
