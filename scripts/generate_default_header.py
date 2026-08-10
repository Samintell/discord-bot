"""
Generate the default B50 header background (assets/shop/header/default.png).

Matches the b50 renderer's header band exactly: 1875x450. The palette
follows the historical fallback fill (240, 210, 230) with a soft vertical
gradient plus a subtle diagonal glow so text/nameplate stays readable.

Usage:
    python scripts/generate_default_header.py
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "assets" / "shop" / "header"
OUT_PATH = OUT_DIR / "default.png"

W, H = 1875, 450


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    from PIL import Image, ImageDraw

    top = (247, 205, 228)
    bottom = (222, 196, 235)

    img = Image.new("RGB", (W, H), (240, 210, 230))
    draw = ImageDraw.Draw(img, "RGBA")

    # soft vertical gradient
    for y in range(H):
        t = y / (H - 1)
        draw.line([(0, y), (W, y)], fill=lerp(top, bottom, t))

    # gentle diagonal light sweep for depth
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, W, 25):
        alpha = int(22 * (1 - abs(x - W / 2) / (W / 2)))
        od.line([(x, 0), (x + H * 0.6, H)], fill=(255, 255, 255, alpha), width=12)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT_PATH)
    print(f"wrote {OUT_PATH}  ({W}x{H})")


if __name__ == "__main__":
    main()
