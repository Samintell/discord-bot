"""
Update script to sync audio files and config between local and remote server.

Remote host is read from REMOTE_HOST in .env or the environment. The SSH
login user cannot write to the bot's home directory, so all remote writes
go through /tmp staging + `sudo mv` (passwordless sudo required); remote
reads use `sudo cat`.

Operations (default):
1. Pull remote config files (aliases/translations replace local entirely,
   remote wins on conflict)
2. Push local profile_shop.json to remote (overrides remote)
3. Push merged config files back to remote
4. Copy audio files from new_songs/ to remote audio/ directory
5. Sync assets/ folder to remote (creates remote folder if missing)

Options:
--audio-only: Only upload new audio files (skip config and assets sync)
"""

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local changes to the remote server.")
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Only upload new audio files from new_songs/.",
    )
    return parser.parse_args()


def run_cmd(cmd, check=True):
    """Run a shell command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result


def scp_pull(remote_path, local_path):
    """Pull a file from remote via sudo cat (remote dirs are not readable by the SSH user)."""
    result = run_cmd(["ssh", REMOTE_HOST, "sudo", "cat", remote_path], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to pull {remote_path}: {result.stderr.strip()}")
    Path(local_path).write_text(result.stdout, encoding="utf-8")


def scp_push(local_path, remote_path):
    """Push a file to remote via /tmp staging + sudo mv (remote dirs are root-only)."""
    tmp_path = f"/tmp/{Path(local_path).name}"
    run_cmd(["scp", str(local_path), f"{REMOTE_HOST}:{tmp_path}"])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "mv", "-f", tmp_path, remote_path])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "chown", "botuser:botuser", remote_path])


def scp_push_dir(local_dir, remote_dir):
    """Push a directory's contents to remote via /tmp staging + sudo mv."""
    files = list(local_dir.iterdir())
    if not files:
        print(f"  (no files in {local_dir})")
        return 0
    file_args = [str(f) for f in files if f.is_file()]
    if file_args:
        for f in file_args:
            tmp_path = f"/tmp/{Path(f).name}"
            run_cmd(["scp", f, f"{REMOTE_HOST}:{tmp_path}"])
            run_cmd(["ssh", REMOTE_HOST, "sudo", "mv", "-f", tmp_path, remote_dir])
    return len(file_args)


def ensure_remote_dir(remote_dir):
    """Ensure a directory exists on the remote (created as botuser via sudo)."""
    run_cmd(["ssh", REMOTE_HOST, "sudo", "mkdir", "-p", remote_dir])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "chown", "-R", "botuser:botuser", remote_dir])


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


def prefer_local(local, remote):
    """Keep local data and ignore remote for overrides like profile_shop.json."""
    return local


def prefer_remote(local, remote):
    """Replace local data entirely with the remote's version."""
    return remote


def sync_configs():
    """Pull remote configs, merge with local, save locally, push merged to remote."""
    config_dir = PROJECT_ROOT / "config"
    config_dir.mkdir(exist_ok=True)

    config_files = {
        "known_translations.json": prefer_remote,
        "romaji_overrides.json": prefer_remote,
        "aliases.json": prefer_remote,
        "profile_shop.json": prefer_local,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for filename, merge_fn in config_files.items():
            local_path = config_dir / filename
            remote_path = f"{REMOTE_DIR}/config/{filename}"
            tmp_path = tmpdir / filename

            print(f"\n  Syncing {filename}...")

            local_data = load_json(local_path)

            # Pull remote version (raises if it can't be read)
            try:
                scp_pull(remote_path, tmp_path)
                remote_data = load_json(tmp_path)
            except RuntimeError as e:
                print(f"    WARNING: could not pull remote copy: {e}")
                print("    Keeping local file and pushing it to remote.")
                remote_data = None

            local_count = len(local_data)
            remote_count = len(remote_data) if remote_data is not None else "n/a"

            # Merge (only when the remote copy was actually read)
            if remote_data is not None:
                merged = merge_fn(local_data, remote_data)
                save_json(local_path, merged)
            else:
                merged = local_data
            merged_count = len(merged)

            print(f"    Local: {local_count}, Remote: {remote_count}, Merged: {merged_count}")

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

    # Push to remote via /tmp staging + sudo mv
    remote_audio = f"{REMOTE_DIR}/audio"
    run_cmd(["ssh", REMOTE_HOST, "sudo", "mkdir", "-p", remote_audio])
    for f in audio_files:
        tmp_path = f"/tmp/{f.name}"
        run_cmd(["scp", str(f), f"{REMOTE_HOST}:{tmp_path}"])
        run_cmd(["ssh", REMOTE_HOST, "sudo", "mv", "-f", tmp_path, remote_audio])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "chown", "-R", "botuser:botuser", remote_audio])
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
    staging = "/tmp/assets_sync"

    print("  Staging assets/ to /tmp on remote...")
    run_cmd(["ssh", REMOTE_HOST, "sudo", "rm", "-rf", staging])
    run_cmd(["scp", "-r", str(local_assets), f"{REMOTE_HOST}:{staging}"])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "rm", "-rf", remote_assets])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "mv", "-T", "-f", staging, remote_assets])
    run_cmd(["ssh", REMOTE_HOST, "sudo", "chown", "-R", "botuser:botuser", remote_assets])
    print("  Synced assets/ to remote.")


def main():
    args = parse_args()
    require_remote_host()
    print("=" * 60)
    print("MaiMai Quiz Bot - Remote Update Script")
    print(f"Remote: {REMOTE_HOST}:{REMOTE_DIR}")
    print("=" * 60)

    if args.audio_only:
        print("\n[1/1] Uploading new audio files...")
        try:
            push_new_audio()
        except Exception as e:
            print(f"\n  ERROR uploading audio: {e}")
    else:
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
