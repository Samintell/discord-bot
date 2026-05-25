"""
Update script to sync audio files and config between local and remote server.

Remote host is read from REMOTE_HOST in .env or the environment.

Operations:
1. Pull remote config files and merge with local (remote wins on conflict)
2. Push local profile_shop.json to remote (overrides remote)
3. Push merged config files back to remote
4. Copy audio files from new_songs/ to remote audio/ directory
5. Sync assets/ folder to remote (creates remote folder if missing)
"""

import json
import os
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
REMOTE_DIR = "/home/botuser/discord-bot"


def load_env_value(key: str) -> str | None:
    env_value = os.environ.get(key)
    if env_value:
        return env_value

    if not ENV_FILE.exists():
        return None

    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return None

    return None


REMOTE_HOST = load_env_value("REMOTE_HOST")


def require_remote_host() -> None:
    if REMOTE_HOST:
        return
    print("ERROR: REMOTE_HOST is not set. Add REMOTE_HOST=... to .env or your environment.")
    sys.exit(1)


def run_cmd(cmd, check=True):
    """Run a shell command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result


def scp_pull(remote_path, local_path):
    """Pull a file from remote via scp."""
    run_cmd(["scp", f"{REMOTE_HOST}:{remote_path}", str(local_path)], check=False)


def scp_push(local_path, remote_path):
    """Push a file to remote via scp."""
    run_cmd(["scp", str(local_path), f"{REMOTE_HOST}:{remote_path}"])


def scp_push_dir(local_dir, remote_dir):
    """Push a directory's contents to remote via scp."""
    files = list(local_dir.iterdir())
    if not files:
        print(f"  (no files in {local_dir})")
        return 0
    file_args = [str(f) for f in files if f.is_file()]
    if file_args:
        run_cmd(["scp"] + file_args + [f"{REMOTE_HOST}:{remote_dir}/"])
    return len(file_args)


def ensure_remote_dir(remote_dir):
    """Ensure a directory exists on the remote host."""
    run_cmd(["ssh", REMOTE_HOST, "mkdir", "-p", remote_dir])


def load_json(path):
    """Load JSON file, returning empty dict/list if missing."""
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_json(path, data):
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def merge_dicts(local, remote):
    """Merge two dicts. Remote entries win on key conflict."""
    merged = dict(local)
    merged.update(remote)
    return merged


def merge_alias_dicts(local, remote):
    """Merge alias dicts (dict of lists). Combines lists per key, deduplicates."""
    all_keys = set(list(local.keys()) + list(remote.keys()))
    merged = {}
    for key in sorted(all_keys):
        local_aliases = local.get(key, [])
        remote_aliases = remote.get(key, [])
        combined = list(dict.fromkeys(local_aliases + remote_aliases))
        if combined:
            merged[key] = combined
    return merged


def prefer_local(local, remote):
    """Keep local data and ignore remote for overrides like profile_shop.json."""
    return local


def sync_configs():
    """Pull remote configs, merge with local, save locally, push merged to remote."""
    config_dir = PROJECT_ROOT / "config"
    config_dir.mkdir(exist_ok=True)

    config_files = {
        "known_translations.json": merge_dicts,
        "romaji_overrides.json": merge_dicts,
        "aliases.json": merge_alias_dicts,
        "profile_shop.json": prefer_local,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for filename, merge_fn in config_files.items():
            local_path = config_dir / filename
            remote_path = f"{REMOTE_DIR}/config/{filename}"
            tmp_path = tmpdir / filename

            print(f"\n  Syncing {filename}...")

            # Pull remote version
            scp_pull(remote_path, tmp_path)

            local_data = load_json(local_path)
            remote_data = load_json(tmp_path)

            local_count = len(local_data)
            remote_count = len(remote_data)

            # Merge
            merged = merge_fn(local_data, remote_data)
            merged_count = len(merged)

            print(f"    Local: {local_count}, Remote: {remote_count}, Merged: {merged_count}")

            # Save merged locally
            save_json(local_path, merged)

            # Push merged to remote
            scp_push(local_path, remote_path)

            print(f"    Done.")


def push_new_audio():
    """Copy audio files from new_songs/ to remote audio/ directory."""
    new_songs_dir = PROJECT_ROOT / "new_songs"

    if not new_songs_dir.exists():
        print("\n  new_songs/ directory does not exist, skipping.")
        return

    audio_files = [f for f in new_songs_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in ('.mp3', '.ogg', '.wav', '.flac')]

    if not audio_files:
        print("\n  No audio files in new_songs/, skipping.")
        return

    print(f"\n  Found {len(audio_files)} audio file(s) to upload:")
    for f in audio_files:
        print(f"    - {f.name}")

    # Also copy to local audio/ directory
    local_audio = PROJECT_ROOT / "audio"
    local_audio.mkdir(exist_ok=True)
    for f in audio_files:
        dest = local_audio / f.name
        if not dest.exists():
            shutil.copy2(f, dest)
            print(f"    Copied to local audio/: {f.name}")

    # Push to remote
    remote_audio = f"{REMOTE_DIR}/audio"
    file_args = [str(f) for f in audio_files]
    run_cmd(["scp"] + file_args + [f"{REMOTE_HOST}:{remote_audio}/"])
    print(f"  Uploaded {len(audio_files)} file(s) to remote audio/.")


def push_assets():
    """Sync assets/ folder to remote."""
    local_assets = PROJECT_ROOT / "assets"
    if not local_assets.exists():
        print("\n  assets/ directory does not exist, skipping.")
        return

    has_files = any(p.is_file() for p in local_assets.rglob("*"))
    if not has_files:
        print("\n  assets/ directory is empty, skipping.")
        return

    remote_assets = f"{REMOTE_DIR}/assets"
    ensure_remote_dir(remote_assets)
    run_cmd(["scp", "-r", str(local_assets), f"{REMOTE_HOST}:{REMOTE_DIR}/"])
    print("  Synced assets/ to remote.")


def main():
    require_remote_host()
    print("=" * 60)
    print("MaiMai Quiz Bot - Remote Update Script")
    print(f"Remote: {REMOTE_HOST}:{REMOTE_DIR}")
    print("=" * 60)

    # Step 1: Sync configs (pull, merge, push)
    print("\n[1/3] Syncing config files...")
    try:
        sync_configs()
    except Exception as e:
        print(f"\n  ERROR syncing configs: {e}")
        print("  Continuing with audio upload...")

    # Step 2: Push new audio files
    print("\n[2/3] Uploading new audio files...")
    try:
        push_new_audio()
    except Exception as e:
        print(f"\n  ERROR uploading audio: {e}")

    # Step 3: Sync assets folder
    print("\n[3/3] Syncing assets folder...")
    try:
        push_assets()
    except Exception as e:
        print(f"\n  ERROR syncing assets: {e}")

    print("\n" + "=" * 60)
    print("Update complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
