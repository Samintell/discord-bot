import asyncio
from pathlib import Path
import sys

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from utils.chart_renderer import ChartRenderer
from utils.song_loader import load_songs, get_song_chart_path

async def test():
    renderer = ChartRenderer()
    await renderer.initialize()
    
    songs = load_songs()
    chart_path = None
    for s in songs:
        cp = get_song_chart_path(s)
        if cp:
            chart_path = Path(cp)
            break
            
    if not chart_path:
        print("No charts found")
        await renderer.close()
        return
    print(f"Rendering chart: {chart_path}")
    
    # Let's add a console listener to the page to see what fillText is receiving
    page = await renderer._get_page()
    page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
    
    # Inject a console.log into fillText
    await page.evaluate("""(() => {
        if (!window.__debugFillText) {
            window.__debugFillText = true;
            const orig = CanvasRenderingContext2D.prototype.fillText;
            CanvasRenderingContext2D.prototype.fillText = function(text, x, y, maxWidth) {
                console.log("fillText called with: '" + text + "'");
                if (maxWidth !== undefined) {
                    return orig.call(this, text, x, y, maxWidth);
                }
                return orig.call(this, text, x, y);
            };
        }
    })()""")
    
    gif_path = await renderer.render_chart_gif(chart_path, excerpt_duration=2.0, fps=5)
    print(f"Rendered to: {gif_path}")
    
    await renderer.close()

if __name__ == "__main__":
    asyncio.run(test())
