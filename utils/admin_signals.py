"""
Admin control signal helpers for cross-process updates.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent
SIGNAL_FILE = PROJECT_ROOT / "config" / "admin_signals.jsonl"


def emit_admin_signal(action: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """Append a control signal to the shared signal file.

    Returns the signal id for logging/troubleshooting.
    """
    SIGNAL_FILE.parent.mkdir(exist_ok=True)
    signal = {
        "id": str(uuid.uuid4()),
        "action": action,
        "payload": payload or {},
        "created_at": int(time.time()),
    }
    with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(signal, ensure_ascii=False) + "\n")
    return signal["id"]


async def watch_admin_signals(
    on_signal: Callable[[Dict[str, Any]], Awaitable[None]],
    poll_interval: float = 3.0,
) -> None:
    """Poll the signal file and dispatch new signals to the callback."""
    last_pos = 0
    if SIGNAL_FILE.exists():
        last_pos = SIGNAL_FILE.stat().st_size

    while True:
        await asyncio.sleep(poll_interval)
        if not SIGNAL_FILE.exists():
            continue

        try:
            with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
                f.seek(last_pos)
                while True:
                    line_start = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        last_pos = f.tell()
                        continue
                    try:
                        signal = json.loads(line)
                    except json.JSONDecodeError:
                        f.seek(line_start)
                        break
                    last_pos = f.tell()
                    await on_signal(signal)
        except Exception:
            continue
