"""
Chart GIF renderer using Playwright and mai-notes.com player.
Generates animated GIF excerpts of MaiMai chart patterns for the chart quiz mode.
"""

import asyncio
import base64
import functools
import io
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
CHARTS_DIR = PROJECT_ROOT / "charts"
GIF_CACHE_DIR = CHARTS_DIR / "gif_cache"
PLAYER_URL = "https://mai-notes.com/player"

# Canvas size for rendering (smaller = much faster screenshots)
CANVAS_SIZE = 300


def extract_chart_notation(simai_data: str) -> str:
    """
    Extract only the raw chart notation from a full simai file.

    The mai-notes.com player expects only the chart data (e.g. "(180){4}1,2,3,...")
    without metadata headers like &title=, &wholebpm=, etc.
    """
    # Find the inote section (inote_5 for master, inote_6 for remaster)
    for key in ("inote_5", "inote_6"):
        pattern = rf"&{key}=(.*?)(?:&\w+=|$)"
        match = re.search(pattern, simai_data, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Fallback: if no &inote_ found, return as-is (might already be raw notation)
    return simai_data.strip()


class ChartRenderer:
    """Manages Playwright browser for rendering chart GIFs."""

    def __init__(self):
        self._browser = None
        self._playwright = None
        self._page = None  # Reusable page with player already loaded

    async def initialize(self) -> None:
        """Launch browser instance. Call once at first use."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )

    async def _get_page(self):
        """Get or create a reusable page with the player loaded."""
        if self._page is not None and not self._page.is_closed():
            return self._page

        if not self._browser:
            await self.initialize()

        self._page = await self._browser.new_page(
            viewport={"width": 600, "height": 800}
        )
        await self._page.goto(PLAYER_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        # Disable unnecessary hints via UI checkboxes to hide BPM, notes, and break counts
        await self._page.evaluate("""(() => {
            const hideSetting = (id) => {
                const el = document.querySelector(id);
                if (el && el.checked) {
                    el.checked = false;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
            };
            hideSetting('#showBpm');
            hideSetting('#showNoteTotal');
            hideSetting('#showBreakCount');
            hideSetting('#showBreakIndex');
        })()""")

        return self._page

    async def close(self) -> None:
        """Close browser instance. Call at bot shutdown."""
        if self._page and not self._page.is_closed():
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def render_chart_gif(
        self,
        chart_path: Path,
        excerpt_duration: float = 7.0,
        fps: int = 10,
    ) -> Optional[Path]:
        """
        Render a random excerpt of a chart as an animated GIF.

        Args:
            chart_path: Path to the simai chart .txt file
            excerpt_duration: Duration of the excerpt in seconds
            fps: Frames per second for the output GIF

        Returns:
            Path to the generated GIF file, or None on failure
        """
        if not self._browser:
            await self.initialize()

        try:
            simai_data = chart_path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Extract only the raw chart notation (no metadata headers)
        chart_notation = extract_chart_notation(simai_data)
        if not chart_notation:
            return None

        # Pick random start position (0%-90% through the chart)
        start_fraction = random.uniform(0.0, 0.9)

        try:
            page = await self._get_page()
            frames = await self._inject_and_capture(
                page, chart_notation, start_fraction, excerpt_duration, fps
            )
        except Exception as e:
            print(f"Error capturing chart frames: {e}")
            # Page may be in a bad state — discard it so next render gets a fresh one
            if self._page and not self._page.is_closed():
                try:
                    await self._page.close()
                except Exception:
                    pass
            self._page = None
            return None

        if not frames or len(frames) < 3:
            return None

        # Compile GIF in a thread to avoid blocking the event loop
        GIF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = (
            GIF_CACHE_DIR
            / f"chart_{int(datetime.now().timestamp())}_{random.randint(0, 9999)}.gif"
        )

        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, functools.partial(self._compile_gif, frames, fps, output_path)
        )
        return output_path if success else None

    async def _inject_and_capture(
        self,
        page,
        chart_notation: str,
        start_fraction: float,
        duration: float,
        fps: int,
    ) -> list:
        """
        Inject chart notation, seek to position, and capture frames using virtual time.

        The page is reused between renders — this method resets playback state,
        injects new chart data, and captures frames without re-navigating.

        Returns:
            List of JPEG frame bytes
        """
        # Reset page state: stop playback and restore native time functions
        await page.evaluate("""(() => {
            const btn = document.querySelector('#playPauseButton');
            if (btn && btn.textContent.includes('Pause')) btn.click();
            if (window.__origPerfNow) performance.now = window.__origPerfNow;
            if (window.__origDateNow) Date.now = window.__origDateNow;
            if (window.__origRAF) window.requestAnimationFrame = window.__origRAF;
        })()""")

        # Inject raw chart notation (no metadata) into the textarea
        await page.fill("#simaiInput", chart_notation)
        await page.evaluate(
            """document.querySelector('#simaiInput')
               .dispatchEvent(new Event('input', {bubbles: true}))"""
        )
        await asyncio.sleep(0.3)

        # Get total measures from the slider
        total_measures = await page.evaluate(
            "parseInt(document.querySelector('#measureSlider').max) || 100"
        )

        if total_measures <= 1:
            return []

        # Seek to random start position
        start_measure = int(total_measures * start_fraction)
        await page.evaluate(
            f"""(() => {{
            const slider = document.querySelector('#measureSlider');
            slider.value = {start_measure};
            slider.dispatchEvent(new Event('input', {{bubbles: true}}));
        }})()"""
        )
        await asyncio.sleep(0.1)

        # Install virtual time control before starting playback.
        # Saves original functions on window so they can be restored for next render.
        await page.evaluate("""(() => {
            window.__origPerfNow = performance.now.bind(performance);
            window.__virtualTime = window.__origPerfNow();

            performance.now = () => window.__virtualTime;

            window.__origDateNow = Date.now;
            const dateOffset = Date.now() - window.__virtualTime;
            Date.now = () => Math.floor(window.__virtualTime + dateOffset);

            window.__origRAF = window.requestAnimationFrame.bind(window);
            window.requestAnimationFrame = function(cb) {
                return window.__origRAF(() => cb(window.__virtualTime));
            };
        })()""")

        # Start playback
        await page.click("#playPauseButton")
        await asyncio.sleep(0.05)

        # Capture frames with fixed time stepping.
        # Use canvas.toDataURL() instead of Playwright screenshot to capture
        # only raw canvas pixels (no DOM artifacts, parent styling, or overlays).
        # Time advance + frame capture combined into a single evaluate call.
        frame_interval_ms = 1000.0 / fps
        total_frames = int(duration * fps)
        frames = []

        for _ in range(total_frames):
            # Advance virtual time, wait for render, and capture canvas pixels
            try:
                data_url = await page.evaluate(
                    f"""(() => {{
                    window.__virtualTime += {frame_interval_ms};
                    return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => {{
                        const c = document.querySelector('#chartCanvas');
                        const ctx = c.getContext('2d');
                        
                        // Calculate percentage
                        const slider = document.querySelector('#measureSlider');
                        const cur = parseInt(slider.value) || 0;
                        const max = parseInt(slider.max) || 100;
                        let pct = Math.floor((cur / max) * 100);
                        if (pct < 0) pct = 0;
                        if (pct > 100) pct = 100;
                        
                        // Draw percentage text on the canvas
                        ctx.save();
                        ctx.fillStyle = '#fff';
                        ctx.strokeStyle = '#000';
                        ctx.lineWidth = 4;
                        ctx.font = 'bold 24px sans-serif';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'top';
                        const text = pct + '%';
                        ctx.strokeText(text, c.width / 2, 20);
                        ctx.fillText(text, c.width / 2, 20);
                        ctx.restore();
                        
                        r(c.toDataURL('image/jpeg', 0.7));
                    }})));
                }})()"""
                )
                frame_bytes = base64.b64decode(data_url.split(',')[1])
                frames.append(frame_bytes)
            except Exception:
                break

        # Stop playback
        try:
            await page.click("#playPauseButton")
        except Exception:
            pass

        return frames

    def _compile_gif(self, frames: list, fps: int, output_path: Path) -> bool:
        """
        Compile JPEG frames into animated GIF.

        Runs in a thread executor to avoid blocking the event loop.

        Returns:
            True on success
        """
        try:
            images = []
            for frame_bytes in frames:
                img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                images.append(img)

            if not images:
                return False

            duration_ms = int(1000 / fps)
            images[0].save(
                str(output_path),
                format="GIF",
                save_all=True,
                append_images=images[1:],
                duration=duration_ms,
                loop=0,
                optimize=False,
            )

            # If too large for Discord (>8MB), halve the resolution
            file_size = output_path.stat().st_size
            if file_size > 8 * 1024 * 1024:
                smaller = []
                for img in images:
                    w, h = img.size
                    smaller.append(img.resize((w // 2, h // 2), Image.LANCZOS))
                smaller[0].save(
                    str(output_path),
                    format="GIF",
                    save_all=True,
                    append_images=smaller[1:],
                    duration=duration_ms,
                    loop=0,
                    optimize=False,
                )

            return True

        except Exception as e:
            print(f"Error compiling GIF: {e}")
            return False
