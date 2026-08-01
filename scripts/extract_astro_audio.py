"""
Extract audio tracks from zipped AstroDX charts into audio/.

Input: a directory of zip files produced by MaichartConverter-style AstroDX
exports (each zip contains maidata.txt + track.mp3 + bg.png). Example:
E:\\Downloads\\Output_MilkBot_NoBGA_JsonLog_Zip_StrictDecimal

Each chart's maidata.txt is parsed for its title, matched against output.json,
and the embedded audio is saved as audio/{image_name}.mp3 so the bot's
get_song_audio_path() finds it. Charts whose titles can't be matched are
still extracted using the cleaned title and listed in the report.

Usage:
    .venv\\Scripts\\python.exe scripts/extract_astro_audio.py <zip_dir>
    .venv\\Scripts\\python.exe scripts/extract_astro_audio.py <zip_dir> --output audio_new --dry-run
"""

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJECT_ROOT / "audio"
OUTPUT_JSON = PROJECT_ROOT / "output.json"

AUDIO_EXTENSIONS = {".mp3", ".ogg", ".m4a", ".wav", ".aac"}
PREFERRED_AUDIO_NAMES = ("track.mp3", "track_music.mp3", "music.mp3", "track.ogg")

TITLE_TAG_RE = re.compile(r"\[[^\]]*\]")


def load_title_index() -> dict:
    """Build a title -> image filename index from output.json."""
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        songs = json.load(f)
    index = {}
    for song in songs:
        title = song.get("title")
        image = song.get("image")
        if title and image and title not in index:
            index[title] = image
    return index


def load_artist_index() -> dict:
    """Build an artist -> image filename index for artists with a single song.

    Used as a last resort when a chart's title is stripped to nothing, since
    an artist with exactly one song can be identified unambiguously.
    """
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        songs = json.load(f)
    images_by_artist = {}
    for song in songs:
        artist = song.get("artist")
        image = song.get("image")
        if artist and image:
            images_by_artist.setdefault(artist, set()).add(image)
    return {a: next(iter(imgs)) for a, imgs in images_by_artist.items() if len(imgs) == 1}


def parse_maidata(zf: zipfile.ZipFile) -> dict:
    """Parse maidata.txt into a dict of its &fields."""
    fields = {}
    try:
        raw = zf.read("maidata.txt").decode("utf-8", errors="replace")
    except KeyError:
        return fields
    for line in raw.splitlines():
        if line.startswith("&") and "=" in line:
            key, _, value = line[1:].partition("=")
            if key and key not in fields:
                fields[key] = value.strip()
    return fields


def title_candidates(title: str) -> list:
    """Progressively cleaned title versions, best match first.

    AstroDX exports tag charts with suffixes like [SD]/[DX] and utage charts
    with leading tags like [協] and trailing [宴]. Real titles can also start
    with brackets (e.g. "[X]"), so tags are only stripped when the untagged
    version doesn't match, and the trailing tag is removed before the leading
    one.
    """
    t = title.strip()
    trailing = re.sub(r"\[[^\]]*\]$", "", t).strip()
    leading = re.sub(r"^\[[^\]]*\]", "", t).strip()
    both = re.sub(r"^\[[^\]]*\]", "", trailing).strip()
    candidates = [t, trailing, leading, both]
    seen = []
    for c in candidates:
        if c not in seen:
            seen.append(c)
    return seen


def fallback_title(candidates: list) -> str:
    """Pick the most-cleaned candidate usable as a filename.

    Pure bracket tags (e.g. "[DX]") are not valid titles on their own.
    """
    for c in reversed(candidates):
        if c and not re.fullmatch(r"\[[^\]]*\]", c):
            return c
    return ""


def find_audio_entry(zf: zipfile.ZipFile):
    """Find the audio file inside a chart zip, preferring track.mp3."""
    names = zf.namelist()
    candidates = [n for n in names if Path(n).suffix.lower() in AUDIO_EXTENSIONS]
    if not candidates:
        return None
    for preferred in PREFERRED_AUDIO_NAMES:
        if preferred in candidates:
            return preferred
    return max(candidates, key=lambda n: zf.getinfo(n).file_size)


def main():
    parser = argparse.ArgumentParser(description="Extract audio from zipped AstroDX charts into audio/")
    parser.add_argument("zip_dir", help="Directory containing the chart .zip files")
    parser.add_argument("--output", default=str(AUDIO_DIR), help="Output audio directory (default: audio/)")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing audio files")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be extracted without writing files")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    zip_dir = Path(args.zip_dir)
    out_dir = Path(args.output)
    if not zip_dir.is_dir():
        print(f"❌ Directory not found: {zip_dir}")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    title_index = load_title_index()
    artist_index = load_artist_index()
    zips = sorted(zip_dir.glob("*.zip"))
    print(f"🎵 Found {len(zips)} chart zip(s) in {zip_dir}")
    print(f"📂 Output: {out_dir}\n")

    extracted = 0
    skipped = 0
    failed = 0
    unmatched = []
    artist_matched = []
    failures = []

    for i, zf_path in enumerate(zips, 1):
        name = zf_path.name
        try:
            with zipfile.ZipFile(zf_path) as zf:
                fields = parse_maidata(zf)
                title = fields.get("title", "")

                audio_entry = find_audio_entry(zf)
                if not audio_entry:
                    print(f"[{i}/{len(zips)}] ⚠️  {name}: no audio file found in zip")
                    failed += 1
                    failures.append((name, "no audio file in zip"))
                    continue

                candidates = title_candidates(title)
                image = next((title_index.get(c) for c in candidates if title_index.get(c)), None)
                clean = fallback_title(candidates)
                note = ""

                if image:
                    out_name = Path(image).with_suffix(".mp3").name
                elif not clean:
                    # Title stripped to nothing - try an unambiguous artist match
                    artist = fields.get("artist", "")
                    artist_image = artist_index.get(artist)
                    if artist_image:
                        out_name = Path(artist_image).with_suffix(".mp3").name
                        artist_matched.append({"zip": name, "title": title, "artist": artist, "image": artist_image})
                        note = " (matched by artist)"
                    else:
                        print(f"[{i}/{len(zips)}] ⚠️  {name}: empty title, cannot name audio")
                        failed += 1
                        failures.append((name, "empty title"))
                        continue
                else:
                    out_name = f"{clean}.mp3"
                    unmatched.append({"zip": name, "title": title, "cleaned": clean})

                out_path = out_dir / out_name
                if out_path.exists() and not args.overwrite:
                    skipped += 1
                    continue

                if args.dry_run:
                    print(f"[{i}/{len(zips)}] ▶  {name} -> {out_name}{note}")
                    extracted += 1
                    continue

                with zf.open(audio_entry) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"[{i}/{len(zips)}] ✅ {name} -> {out_name}{note}")
                extracted += 1

        except Exception as e:
            print(f"[{i}/{len(zips)}] ❌ {name}: {e}")
            failed += 1
            failures.append((name, str(e)))

    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"  ✅ Extracted: {extracted}")
    print(f"  ⏭️  Skipped (already exists): {skipped}")
    print(f"  ❌ Failed: {failed}")
    if unmatched:
        print(f"\n⚠️  {len(unmatched)} chart(s) could not be matched to output.json and were named by title:")
        for u in unmatched:
            print(f"  - {u['zip']}: {u['title']} -> {u['cleaned']}.mp3")
    if artist_matched:
        print(f"\n🎨 {len(artist_matched)} chart(s) were matched by unique artist:")
        for a in artist_matched:
            print(f"  - {a['zip']}: {a['title']} by {a['artist']} -> {a['image']}")
    if failures:
        print(f"\n❌ Failures ({len(failures)}):")
        for f_zip, reason in failures:
            print(f"  - {f_zip}: {reason}")


if __name__ == "__main__":
    main()
