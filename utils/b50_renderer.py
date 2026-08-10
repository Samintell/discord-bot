import io
import math
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

from utils.profile_shop import get_shop_item

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "images"
SHOP_ASSETS_DIR = PROJECT_ROOT / "assets" / "shop"

# Canvas is rendered natively at final output size (no upscaling).
# Layout was previously designed at 1250x2020 then resized x1.5; these
# values are that design space hardcoded at 1.5x scale.
CANVAS_W, CANVAS_H = 1875, 3030
HEADER_H = 450
NAME_RECT = (105, 105, 1025, 360)
AVATAR_RECT = (165, 143, 345, 323)
USER_POS = (375, 135)
RATE_RECT = (375, 218, 975, 335)
NEW_TITLE_POS = (75, 470)
OLD_TITLE_POS = (75, 1281)
PANEL_W, PANEL_H = 315, 195
GAP = 37
GRID_X = 75
NEW_GRID_Y = 555
OLD_GRID_Y = 1356
TOP15_ROWS, TOP35_ROWS = 3, 7
COLS = 5

def get_rating_color(rating: int) -> str:
    if rating >= 15000: return "rainbow"
    if rating >= 14500: return "platinum"
    if rating >= 14000: return "gold"
    if rating >= 13000: return "silver"
    if rating >= 12000: return "bronze"
    if rating >= 10000: return "purple"
    if rating >= 7000: return "red"
    if rating >= 4000: return "yellow"
    if rating >= 2000: return "green"
    if rating >= 1000: return "blue"
    return "white"

def get_rating_color(rating: int) -> str:
    if rating >= 15000: return "rainbow"
    if rating >= 14500: return "platinum"
    if rating >= 14000: return "gold"
    if rating >= 13000: return "silver"
    if rating >= 12000: return "bronze"
    if rating >= 10000: return "purple"
    if rating >= 7000: return "red"
    if rating >= 4000: return "yellow"
    if rating >= 2000: return "green"
    if rating >= 1000: return "blue"
    return "white"

def get_font(size: int, bold: bool = False, family: str = "japanese") -> ImageFont.FreeTypeFont:
    """Try to load a local font from assets, fallback to system fonts."""
    fonts_dir = PROJECT_ROOT / "assets" / "fonts"
    
    try:
        if family == "english":
            font_path = fonts_dir / ("Torus-Bold.otf" if bold else "Torus-SemiBold.otf")
            return ImageFont.truetype(str(font_path), size)
        else:
            font_path = fonts_dir / "NotoSansCJKjp-Bold.otf"
            return ImageFont.truetype(str(font_path), size)
    except IOError:
        pass
        
    try:
        # Prefer Meiryo Bold or MS Gothic for thicker text as fallback
        font_name = "meiryob.ttc" if bold else "meiryo.ttc"
        return ImageFont.truetype(font_name, size)
    except IOError:
        try:
            font_name = "msgothic.ttc"
            return ImageFont.truetype(font_name, size)
        except IOError:
            try:
                font_name = "arialbd.ttf" if bold else "arial.ttf"
                return ImageFont.truetype(font_name, size)
            except IOError:
                return ImageFont.load_default()

def truncate_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Truncates text to fit within max_width using the given font."""
    if not text:
        return ""
    # PIL <= 9.x: textsize, >= 10.x: textbbox
    def get_width(t):
        if hasattr(font, 'getbbox'):
            return font.getbbox(t)[2] - font.getbbox(t)[0]
        else:
            return font.getsize(t)[0]

    if get_width(text) <= max_width:
        return text
    
    truncated = text
    while get_width(truncated + "...") > max_width and len(truncated) > 0:
        truncated = truncated[:-1]
    return truncated + "..."

class B50Renderer:
    def __init__(self, username: str, language: str, top_15: List[Dict], top_35: List[Dict], 
                 total_rating: int, avatar_bytes: Optional[bytes] = None, 
                 banner_id: Optional[str] = None, partner_id: Optional[str] = None,
                 header_id: Optional[str] = None):
        self.username = username
        self.language = language
        self.top_15 = top_15
        self.top_35 = top_35
        self.total_rating = total_rating
        self.avatar_bytes = avatar_bytes
        self.banner_id = banner_id
        self.partner_id = partner_id
        self.header_id = header_id
        
        self.width = CANVAS_W
        self.height = CANVAS_H
        self.bg_color = (250, 250, 250)

    def _resolve_header_path(self) -> Optional[Path]:
        """Resolve the equipped header image, falling back to the default."""
        if self.header_id:
            item = get_shop_item(self.header_id)
            if item:
                image_path = item.get("image_path")
                if image_path:
                    path = Path(image_path)
                    if not path.is_absolute():
                        path = PROJECT_ROOT / path
                    if path.exists():
                        return path
            path = SHOP_ASSETS_DIR / "header" / f"{self.header_id}.png"
            if path.exists():
                return path
        default = SHOP_ASSETS_DIR / "header" / "default.png"
        return default if default.exists() else None

    def _load_header(self, width: int, height: int) -> Optional[Image.Image]:
        """Load the header image, cover-cropped to the given size."""
        path = self._resolve_header_path()
        if not path:
            return None
        try:
            header = Image.open(path).convert("RGBA")
            # Crop to cover the full header band
            header_aspect = header.width / header.height
            target_aspect = width / height
            if header_aspect > target_aspect:
                new_width = int(header.height * target_aspect)
                offset = (header.width - new_width) // 2
                header = header.crop((offset, 0, offset + new_width, header.height))
            else:
                new_height = int(header.width / target_aspect)
                offset = (header.height - new_height) // 2
                header = header.crop((0, offset, header.width, offset + new_height))
            return header.resize((width, height), Image.LANCZOS)
        except Exception as e:
            print(f"Failed to load header {path}: {e}")
            return None

    def _draw_song_panel(self, song: Dict, width: int, height: int) -> Image.Image:
        panel = Image.new("RGBA", (width, height), (40, 40, 50, 255))
        draw = ImageDraw.Draw(panel)
        
        # Draw cover image
        image_path = None
        if song.get("image"):
            image_path = IMAGES_DIR / song["image"]
            
        if image_path and image_path.exists():
            try:
                cover = Image.open(image_path).convert("RGBA")
                # Crop to fit
                cover_aspect = cover.width / cover.height
                target_aspect = width / height
                if cover_aspect > target_aspect:
                    new_width = int(cover.height * target_aspect)
                    offset = (cover.width - new_width) // 2
                    cover = cover.crop((offset, 0, offset + new_width, cover.height))
                else:
                    new_height = int(cover.width / target_aspect)
                    offset = (cover.height - new_height) // 2
                    cover = cover.crop((0, offset, cover.width, offset + new_height))
                    
                cover = cover.resize((width, height), Image.LANCZOS)
                
                # Blur the song image
                cover = cover.filter(ImageFilter.GaussianBlur(radius=4))
                
                # Make the song images slightly brighter than before
                enhancer = ImageEnhance.Brightness(cover)
                cover = enhancer.enhance(0.55)
                
                panel.paste(cover, (0, 0))
            except Exception as e:
                print(f"Failed to load cover {image_path}: {e}")
                
        # Determine title based on language
        title = song.get("song_name", "Unknown")
        if self.language == "english":
            if song.get("english"):
                title = song["english"]
            elif song.get("romaji"):
                title = song["romaji"]
        elif self.language == "romaji" and song.get("romaji"):
            title = song["romaji"]
            
        # Draw Title
        title_font = get_font(27, bold=True)
        title_disp = truncate_text(draw, title, title_font, width - 15)
        draw.text((8, 8), title_disp, font=title_font, fill=(255, 255, 255))
        
        # Difficulty and Type indicator
        diff_colors = {
            "basic": (118, 192, 0),
            "advanced": (233, 178, 0),
            "expert": (224, 76, 76),
            "master": (148, 50, 194),
            "remaster": (255, 255, 255)
        }
        diff = song.get("difficulty", "master")
        color = diff_colors.get(diff, (255, 255, 255))
        
        type_str = song.get("chart_type", "std").upper()
        draw.rectangle([8, 45, 72, 75], fill=color, outline=(0,0,0), width=2)
        type_font = get_font(24, bold=True, family="english")
        text_color = (0, 0, 0) if diff == "remaster" or diff == "advanced" else (255, 255, 255)
        draw.text((15, 47), type_str, font=type_font, fill=text_color)
        
        # Bottom left: Achievement and Rank
        achieve = f"{song.get('achievement', 0):.4f}%"
        achieve_font = get_font(27, bold=True, family="english")
        draw.text((8, height - 39), achieve, font=achieve_font, fill=(255, 255, 255))
        
        # Render Rank text based on achievement
        rank = ""
        a = song.get('achievement', 0)
        if a >= 100.5: rank = "SSS+"
        elif a >= 100.0: rank = "SSS"
        elif a >= 99.5: rank = "SS+"
        elif a >= 99.0: rank = "SS"
        elif a >= 98.0: rank = "S+"
        elif a >= 97.0: rank = "S"
        elif a >= 94.0: rank = "AAA"
        elif a >= 90.0: rank = "AA"
        elif a >= 80.0: rank = "A"
        
        rank_font = get_font(48, bold=True, family="english")
        rank_color = (255, 215, 0) if "S" in rank else (220, 220, 220)
        draw.text((8, height - 93), rank, font=rank_font, fill=rank_color)
        
        # Bottom right: Rating
        rating = str(song.get("rating", 0))
        rating_font = get_font(57, bold=True, family="english")
        
        def get_width(f, t):
            if hasattr(f, 'getbbox'):
                return f.getbbox(t)[2] - f.getbbox(t)[0]
            else:
                return f.getsize(t)[0]
                
        r_w = get_width(rating_font, rating)
        draw.text((width - r_w - 12, height - 68), rating, font=rating_font, fill=(255, 255, 255))
        
        # Level text above rating
        level_str = str(song.get("level", 0))
        level_font = get_font(30, bold=True, family="english")
        l_w = get_width(level_font, level_str)
        draw.text((width - l_w - 12, height - 105), level_str, font=level_font, fill=(255, 255, 255))
        
        # Draw a neat border around the whole panel
        draw.rectangle([0, 0, width-1, height-1], outline=(200, 200, 200), width=2)
        
        return panel

    def render(self) -> io.BytesIO:
        img = Image.new("RGBA", (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw Banner / Background header
        header_height = HEADER_H
        header = self._load_header(self.width, header_height)
        if header:
            img.paste(header, (0, 0))
        else:
            draw.rectangle([0, 0, self.width, header_height], fill=(240, 210, 230))
        
        # Draw white background wrapper for nameplate
        # Covers from 105,105 to 1200, 360
        draw.rounded_rectangle(NAME_RECT, radius=23, fill=(255, 255, 255))
        
        # User Avatar
        if self.avatar_bytes:
            avatar_img = Image.open(io.BytesIO(self.avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((180, 180), Image.LANCZOS)
            
            # Mask to circle
            mask = Image.new('L', (180, 180), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 180, 180), fill=255)
            
            img.paste(avatar_img, (165, 143), mask)
        else:
            draw.ellipse(AVATAR_RECT, fill=(100, 100, 100))
            
        # Draw user name
        user_font = get_font(63, bold=True)
        draw.text(USER_POS, self.username, font=user_font, fill=(50, 50, 50))
        
        # Draw rating plate
        rating_color = get_rating_color(self.total_rating)
        try:
            rating_base = Image.open(PROJECT_ROOT / "assets" / "rating" / f"{rating_color}.webp").convert("RGBA")
            # Original rating plate is 664x130. Scale down to fit.
            w, h = rating_base.size
            new_w = 600
            new_h = int(h * (new_w / w)) # ~117
            rating_base = rating_base.resize((new_w, new_h), Image.LANCZOS)
            img.paste(rating_base, (375, 218), rating_base)
            
            # Put the text directly on top of the plate, aligning each digit perfectly in its box
            rating_str = str(self.total_rating)
            
            # The X centers of the 5 digit boxes in the original 664px image
            original_centers = [337, 389, 441, 494, 546]
            used_centers = original_centers[-len(rating_str):]
            
            # The Y center of the boxes in the original 664x130 image is at Y=54
            center_y = 218 + (54 * (new_h / h))
            
            for i, digit in enumerate(rating_str):
                center_x = 375 + (used_centers[i] * (new_w / w))
            
            # Put the text directly on top of the plate, aligning each digit perfectly in its box
            total_font = get_font(54, bold=True, family="english")
            rating_str = str(self.total_rating)
            
            # The X centers of the 5 digit boxes in the original 664px image
            original_centers = [337, 389, 441, 494, 546]
            used_centers = original_centers[-len(rating_str):]
            
            # The Y center of the boxes in the original 664x130 image is at Y=54
            # We add +9 to shift the numbers slightly down based on visual feedback
            center_y = 218 + (54 * (new_h / h)) + 9
            
            for i, digit in enumerate(rating_str):
                center_x = 375 + (used_centers[i] * (new_w / w))
                
                if hasattr(total_font, 'getbbox'):
                    bbox = total_font.getbbox(digit)
                    d_w = bbox[2] - bbox[0]
                    d_h = bbox[3] - bbox[1]
                    offset_x = bbox[0]
                    offset_y = bbox[1]
                else:
                    d_w = total_font.getsize(digit)[0]
                    d_h = total_font.getsize(digit)[1]
                    offset_x, offset_y = 0, 0
                    
                draw_x = center_x - (d_w / 2) - offset_x
                draw_y = center_y - (d_h / 2) - offset_y
                draw.text((draw_x, draw_y), digit, font=total_font, fill=(255, 255, 255))
        except Exception as e:
            # Fallback if image fails
            total_font = get_font(54, bold=True, family="english")
            draw.text((375, 225), f"Rating: {self.total_rating}", font=total_font, fill=(255, 215, 0))
        
        # Draw New Charts Section
        section_font = get_font(45, bold=True, family="english")
        draw.text(NEW_TITLE_POS, f"NEW CHARTS (Top 15) - Total: {sum(s['rating'] for s in self.top_15)}", font=section_font, fill=(50, 150, 200))
        
        panel_w = PANEL_W
        panel_h = PANEL_H
        gap_x = GAP
        gap_y = GAP
        
        start_y = NEW_GRID_Y
        start_x = GRID_X
        
        for i, song in enumerate(self.top_15):
            row = i // COLS
            col = i % COLS
            x = start_x + col * (panel_w + gap_x)
            y = start_y + row * (panel_h + gap_y)
            panel = self._draw_song_panel(song, panel_w, panel_h)
            img.paste(panel, (x, y))
            
        # Draw Old Charts Section
        old_start_y = start_y + TOP15_ROWS * (panel_h + gap_y) + 30
        draw.text(OLD_TITLE_POS, f"OLD CHARTS (Top 35) - Total: {sum(s['rating'] for s in self.top_35)}", font=section_font, fill=(180, 80, 150))
        
        old_grid_y = OLD_GRID_Y
        for i, song in enumerate(self.top_35):
            row = i // COLS
            col = i % COLS
            x = start_x + col * (panel_w + gap_x)
            y = old_grid_y + row * (panel_h + gap_y)
            panel = self._draw_song_panel(song, panel_w, panel_h)
            img.paste(panel, (x, y))

        # Output to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
