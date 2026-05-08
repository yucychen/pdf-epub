"""用 Pillow 生成应用图标 (assets/icon.ico / icon.icns / icon.png)"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "assets"
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    radius = size // 5
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=radius, fill=(43, 108, 176, 255))
    text = "P>E"
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.42))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - size * 0.03),
           text, font=font, fill=(255, 255, 255, 255))
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    images = [draw_icon(s) for s in SIZES]
    images[-1].save(os.path.join(OUT_DIR, "icon.png"))
    images[-2].save(os.path.join(OUT_DIR, "icon.ico"),
                    sizes=[(s, s) for s in SIZES if s <= 256])
    if sys.platform == "darwin" or os.environ.get("FORCE_ICNS"):
        try:
            images[-1].save(os.path.join(OUT_DIR, "icon.icns"))
        except Exception as e:
            print("icns generation failed (non-fatal):", e)
    print("Icons generated in", OUT_DIR)


if __name__ == "__main__":
    main()
