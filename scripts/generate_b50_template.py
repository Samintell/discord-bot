"""
Generate annotated B50 layout templates for background artists.

All geometry is imported from B50Renderer (utils/b50_renderer.py), which
renders natively at final output size:

    canvas 1875x3030
    header band y 0-450
    nameplate (105,105) -> (1200,360), white, radius 23
    avatar 180px circle at (165,143)
    username 63px bold at (375,135)
    rating plate 600x117 at (375,218)
    song panels 315x195, 37px gaps, grid starts at x=75
      NEW CHARTS: 3 rows, first row at y=555
      OLD CHARTS: 7 rows, first row at y=1356

Outputs (references/):
    b50_template.png        canvas blueprint at native resolution
    b50_panel_detail.png    one song panel magnified 3x with inner layout

Usage:
    python scripts/generate_b50_template.py
"""

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageDraw

from utils.b50_renderer import (
    CANVAS_W, CANVAS_H, HEADER_H, NAME_RECT, AVATAR_RECT, USER_POS,
    RATE_RECT, NEW_TITLE_POS, OLD_TITLE_POS, PANEL_W, PANEL_H, GAP,
    GRID_X, NEW_GRID_Y, OLD_GRID_Y, TOP15_ROWS, TOP35_ROWS, COLS,
    get_font,
)

OUT_DIR = PROJECT_ROOT / "references"

NEW_COL = (50, 150, 200)
OLD_COL = (190, 90, 160)
DIM_COL = (200, 60, 60)


def text_width(font, text):
    b = font.getbbox(text)
    return b[2] - b[0]


def chip(d, cx, cy, text, font, fill=(255, 255, 255, 225), tcol=(35, 35, 35), pad=5):
    """Semi-opaque rounded label centered at (cx, cy)."""
    w = text_width(font, text)
    bb = font.getbbox(text)
    th = bb[3] - bb[1]
    top = cy - th / 2 - bb[1]
    d.rounded_rectangle(
        [cx - w / 2 - pad, top - pad, cx + w / 2 + pad, top + th + pad],
        radius=3, fill=fill, outline=(0, 0, 0, 60),
    )
    d.text((cx - w / 2, top), text, font=font, fill=tcol)


def draw_blueprint() -> Image.Image:
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (240, 240, 242, 255))
    d = ImageDraw.Draw(img)

    f = lambda px: get_font(px, bold=True, family="english")
    fs = lambda px: get_font(px, bold=False, family="english")

    # faint 25px design grid
    for gx in range(0, CANVAS_W, 25):
        a = 45 if gx % 125 == 0 else 18
        d.line([gx, 0, gx, CANVAS_H], fill=(0, 0, 0, a))
    for gy in range(0, CANVAS_H, 25):
        a = 45 if gy % 125 == 0 else 18
        d.line([0, gy, CANVAS_W, gy], fill=(0, 0, 0, a))

    # --- header zone ---
    d.rectangle([0, 0, CANVAS_W, HEADER_H], fill=(240, 210, 230, 110))
    d.rectangle([0, 0, CANVAS_W - 1, HEADER_H - 1], outline=(210, 60, 130), width=2)
    chip(d, 900, 38, "HEADER ZONE  y 0-450 - art is fully visible here",
         f(33), tcol=(190, 20, 90))

    def dashed_rect(box, fill, width):
        x0, y0, x1, y1 = box
        dash, gap = 10, 6
        edges = [
            ((x0, y0), (x1, y0)),
            ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)),
            ((x0, y1), (x0, y0)),
        ]
        for (xa, ya), (xb, yb) in edges:
            length = math.hypot(xb - xa, yb - ya)
            ux, uy = (xb - xa) / length, (yb - ya) / length
            pos = 0.0
            while pos < length:
                end = min(pos + dash, length)
                d.line([xa + ux * pos, ya + uy * pos, xa + ux * end, ya + uy * end],
                       fill=fill, width=width)
                pos = end + gap

    dashed_rect(NAME_RECT, (50, 80, 220), 2)
    chip(d, 652, 108, "nameplate (105,105)->(1200,360) white rounded r23", fs(20))

    d.ellipse(AVATAR_RECT, outline=(240, 130, 0), width=2)
    chip(d, 360, 255, "avatar 180px circle @ (165,143)", fs(18))

    dashed_rect((USER_POS[0], USER_POS[1], 705, 203), (40, 160, 60), 1)
    chip(d, 840, 168, "username 63px bold @ (375,135)", fs(18))

    dashed_rect(RATE_RECT, (220, 60, 60), 1)
    chip(d, 990, 292, "rating plate 600x117 @ (375,218)", fs(18))

    # --- section titles ---
    chip(d, NEW_TITLE_POS[0] + 68, NEW_TITLE_POS[1] + 22, "NEW CHARTS title @ (75,470)  45px", f(23))
    chip(d, OLD_TITLE_POS[0] + 68, OLD_TITLE_POS[1] + 22, "OLD CHARTS title @ (75,1281)  45px", f(23))

    # --- panel grids ---
    def draw_grid(rows, y0, col, rows_label):
        for r in range(rows):
            for c in range(COLS):
                x = GRID_X + c * (PANEL_W + GAP)
                y = y0 + r * (PANEL_H + GAP)
                d.rectangle([x, y, x + PANEL_W, y + PANEL_H],
                            fill=(40, 40, 50, 150), outline=col, width=2)
                if c == 0:
                    chip(d, x + 93, y + 27, f"{rows_label} {r + 1}", fs(20),
                         fill=(255, 255, 255, 170))

    draw_grid(TOP15_ROWS, NEW_GRID_Y, NEW_COL, "NEW")
    draw_grid(TOP35_ROWS, OLD_GRID_Y, OLD_COL, "OLD")
    chip(d, GRID_X + PANEL_W // 2, NEW_GRID_Y + PANEL_H // 2, f"{PANEL_W}x{PANEL_H}", f(30))

    # --- dimension annotations ---
    def dim_h(x0, x1, y, label):
        d.line([x0, y, x1, y], fill=DIM_COL, width=1)
        for xe in (x0, x1):
            d.line([xe, y - 3, xe, y + 3], fill=DIM_COL, width=1)
        chip(d, (x0 + x1) / 2, y, label, fs(20))

    def dim_v(y0, y1, x, label):
        d.line([x, y0, x, y1], fill=DIM_COL, width=1)
        for ye in (y0, y1):
            d.line([x - 3, ye, x + 3, ye], fill=DIM_COL, width=1)
        chip(d, x, (y0 + y1) / 2, label, fs(20))

    dim_h(0, GRID_X, 768, "75")                       # left margin
    right_edge = GRID_X + COLS * PANEL_W + (COLS - 1) * GAP
    dim_h(right_edge, CANVAS_W, 768, "77")            # right margin
    col_gap_x = GRID_X + PANEL_W
    dim_h(col_gap_x, col_gap_x + GAP, 768, "37")      # column gap
    row_gap_y = NEW_GRID_Y + PANEL_H
    dim_v(row_gap_y, row_gap_y + GAP, 90, "37")       # row gap
    dim_v(HEADER_H, NEW_GRID_Y, CANVAS_W - 40, "105")  # header to first grid
    old_row_gap = OLD_GRID_Y + PANEL_H
    dim_v(old_row_gap, old_row_gap + GAP, CANVAS_W - 40, "37")
    old_bottom = OLD_GRID_Y + (TOP35_ROWS - 1) * (PANEL_H + GAP) + PANEL_H
    dim_v(old_bottom, CANVAS_H, CANVAS_W - 40, "87")  # bottom margin

    chip(d, CANVAS_W / 2, CANVAS_H - 25,
         f"PANEL {PANEL_W}x{PANEL_H} . GAP {GAP} . SIDE MARGIN ~75 . header 0-{HEADER_H} . canvas {CANVAS_W}x{CANVAS_H}",
         f(23))
    return img


def draw_panel_detail() -> Image.Image:
    S = 3
    PAD_X, PAD_Y = 260, 120
    pw, ph = PANEL_W * S, PANEL_H * S
    sheet_w, sheet_h = pw + PAD_X * 2, ph + PAD_Y * 2
    img = Image.new("RGBA", (sheet_w, sheet_h), (245, 245, 248, 255))
    d = ImageDraw.Draw(img)

    for gx in range(0, sheet_w, 25):
        a = 40 if gx % 125 == 0 else 15
        d.line([gx, 0, gx, sheet_h], fill=(0, 0, 0, a))
    for gy in range(0, sheet_h, 25):
        a = 40 if gy % 125 == 0 else 15
        d.line([0, gy, sheet_w, gy], fill=(0, 0, 0, a))

    px, py = PAD_X, PAD_Y
    d.rectangle([px, py, px + pw, py + ph], fill=(40, 40, 50), outline=(200, 200, 200), width=2)

    fs = lambda px_: get_font(px_, bold=False, family="english")
    fb = lambda px_: get_font(px_, bold=True, family="english")

    # --- panel elements at 3x, scaled from the renderer's panel layout ---
    d.text((px + 30, py + 30), "cover art: blurred (r=4) brightness 0.55 - fills whole panel",
           font=fs(20), fill=(190, 190, 200))

    d.text((px + 15, py + 15), "Song Title", font=fb(81), fill=(255, 255, 255))
    d.rectangle([px + 24, py + 135, px + 216, py + 225], fill=(148, 50, 194),
                outline=(0, 0, 0), width=2)
    d.text((px + 45, py + 144), "MAS", font=fb(72), fill=(255, 255, 255))
    d.text((px + 15, py + 399), "SSS+", font=fb(144), fill=(255, 215, 0))
    d.text((px + 15, py + 468), "100.0000%", font=fb(81), fill=(255, 255, 255))

    level = "14+"
    lw = text_width(fb(90), level)
    d.text((px + pw - lw - 36, py + 270), level, font=fb(90), fill=(255, 255, 255))
    rating = "12345"
    rw = text_width(fb(171), rating)
    d.text((px + pw - rw - 36, py + 381), rating, font=fb(171), fill=(255, 255, 255))

    # --- annotations with leader lines ---
    def leader(ax, ay, lx, ly):
        d.line([ax, ay, lx, ly], fill=(120, 120, 120), width=1)

    left = [
        (px + 20, py + 50, "title 27px @ (8,8)", 50),
        (px + 30, py + 200, "type box (8,45)-(72,75) . 24px chart type", 195),
        (px + 20, py + 445, "rank 48px @ (8,133) . gold if S*", 445),
        (px + 30, py + 510, "achievement 27px @ (8,156)", 510),
    ]
    for ax, ay, text, cy in left:
        leader(ax, ay, PAD_X - 40, PAD_Y + cy)
        chip(d, 120, PAD_Y + cy, text, fs(16), pad=4)

    right = [
        (px + pw - 36, py + 300, "level 30px @ (x=w-12, y=90) right-aligned", 295),
        (px + pw - 36, py + 430, "rating 57px @ (x=w-12, y=127) right-aligned", 430),
    ]
    for ax, ay, text, cy in right:
        leader(ax, ay, PAD_X + pw + 40, PAD_Y + cy)
        chip(d, sheet_w - 120, PAD_Y + cy, text, fs(16), pad=4)

    chip(d, PAD_X + pw // 2, 40, f"SONG PANEL  {PANEL_W}x{PANEL_H} px", fb(33))
    chip(d, PAD_X + pw // 2, PAD_Y + ph + 40,
         "2px border (200,200,200) . panel bg (40,40,50) . cover image at 0,0 full panel",
         fs(20))
    chip(d, sheet_w - 120, sheet_h - 28, "fonts per renderer get_font() (japanese/english)",
         fs(18), pad=4)
    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    path = OUT_DIR / "b50_template.png"
    img = draw_blueprint()
    img.save(path)
    print(f"wrote {path}  ({img.width}x{img.height})")

    path = OUT_DIR / "b50_panel_detail.png"
    draw_panel_detail().save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
