"""Turn any image (AI-generated or your own product photo) into a finished, on-brand post graphic:
correct platform size, brand colours, headline text, logo. Pure Pillow — works on any computer."""
from __future__ import annotations

import re
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import OUTPUT_DIR

SIZES = {"1:1 (feed)": (1080, 1080), "4:5 (IG portrait)": (1080, 1350),
         "9:16 (Reels/TikTok/Stories)": (1080, 1920), "2:3 (Pinterest)": (1000, 1500),
         "16:9 (banner)": (1920, 1080)}

LAYOUTS = ["Bottom band", "Full-bleed overlay", "Split (photo top, text bottom)", "Framed poster",
           "Photo only + logo"]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _hex(c: str, default=(17, 17, 17)) -> tuple[int, int, int]:
    try:
        if c.strip().lower().startswith("rgb"):
            nums = [float(x) for x in re.findall(r"[\d.]+", c)[:3]]
            return tuple(int(round(n)) for n in nums)
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return default


def _font(size: int, path: str = "") -> ImageFont.FreeTypeFont:
    for p in ([path] if path else []) + FONT_CANDIDATES:
        if p and Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_text(draw, text, max_w, max_h, start, font_path, min_size=28, spacing=1.12):
    size = start
    while size >= min_size:
        f = _font(size, font_path)
        lines = _wrap(draw, text, f, max_w)
        h = len(lines) * size * spacing
        if h <= max_h and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines, size
        size -= 4
    f = _font(min_size, font_path)
    return f, _wrap(draw, text, f, max_w), min_size


def _draw_block(draw, lines, font, size, x, y, color, align="left", width=0, spacing=1.12):
    for i, line in enumerate(lines):
        lx = x
        if align == "center":
            lx = x + (width - draw.textlength(line, font=font)) / 2
        draw.text((lx, y + i * size * spacing), line, font=font, fill=color)


def compose(image: Image.Image, headline: str = "", subtext: str = "", handle: str = "",
            size_key: str = "4:5 (IG portrait)", layout: str = "Bottom band", colors: dict | None = None,
            font_path: str = "", logo_path: str = "", uppercase: bool = True) -> str:
    colors = colors or {}
    primary, secondary, accent = (_hex(colors.get("primary", "#111111")),
                                  _hex(colors.get("secondary", "#F2EDE4"), (242, 237, 228)),
                                  _hex(colors.get("accent", "#E4572E"), (228, 87, 46)))
    W, H = SIZES.get(size_key, (1080, 1350))
    pad = int(W * 0.06)
    headline = headline.upper() if uppercase else headline
    image = image.convert("RGB")

    if layout == "Split (photo top, text bottom)":
        canvas = Image.new("RGB", (W, H), secondary)
        ph = int(H * 0.68)
        canvas.paste(ImageOps.fit(image, (W, ph), Image.LANCZOS), (0, 0))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, ph, W, ph + 10], fill=accent)
        f, lines, s = _fit_text(d, headline, W - 2 * pad, (H - ph) * 0.5, int(W * 0.09), font_path)
        _draw_block(d, lines, f, s, pad, ph + pad * 0.8, primary)
        if subtext:
            sf = _font(int(W * 0.032), font_path)
            sl = _wrap(d, subtext, sf, W - 2 * pad)
            _draw_block(d, sl, sf, int(W * 0.032), pad, ph + pad * 0.8 + len(lines) * s * 1.12 + 16, primary)
    elif layout == "Framed poster":
        canvas = Image.new("RGB", (W, H), secondary)
        frame = int(W * 0.07)
        top_text_h = int(H * 0.16) if headline else 0
        inner = (W - 2 * frame, H - 2 * frame - top_text_h - int(H * 0.05))
        canvas.paste(ImageOps.fit(image, inner, Image.LANCZOS), (frame, frame + top_text_h))
        d = ImageDraw.Draw(canvas)
        if headline:
            f, lines, s = _fit_text(d, headline, W - 2 * frame, top_text_h - 10, int(W * 0.1), font_path)
            _draw_block(d, lines, f, s, frame, frame - 10, primary, "center", W - 2 * frame)
        bottom = f"{subtext}   {handle}".strip()
        if bottom:
            bf = _font(int(W * 0.028), font_path)
            d.text((frame, H - frame - int(W * 0.03)), bottom, font=bf, fill=primary)
    else:
        canvas = ImageOps.fit(image, (W, H), Image.LANCZOS)
        d = ImageDraw.Draw(canvas)
        if layout == "Bottom band" and (headline or subtext):
            band_h = int(H * 0.24)
            band = Image.new("RGB", (W, band_h), primary)
            canvas.paste(band, (0, H - band_h))
            d.rectangle([0, H - band_h, W, H - band_h + 8], fill=accent)
            f, lines, s = _fit_text(d, headline, W - 2 * pad, band_h * 0.55, int(W * 0.085), font_path)
            _draw_block(d, lines, f, s, pad, H - band_h + pad * 0.6, secondary)
            if subtext:
                sf = _font(int(W * 0.03), font_path)
                d.text((pad, H - band_h + pad * 0.6 + len(lines) * s * 1.12 + 6), subtext, font=sf, fill=secondary)
        elif layout == "Full-bleed overlay" and (headline or subtext):
            grad = Image.new("L", (1, 256))
            for y in range(256):
                grad.putpixel((0, y), int(max(0, (y - 90)) * 1.4))
            mask = grad.resize((W, H))
            shade = Image.new("RGB", (W, H), primary)
            canvas = Image.composite(shade, canvas, mask)
            d = ImageDraw.Draw(canvas)
            f, lines, s = _fit_text(d, headline, W - 2 * pad, H * 0.3, int(W * 0.11), font_path)
            sub_h = int(W * 0.035) * 2 if subtext else 0
            y0 = H - pad - sub_h - len(lines) * s * 1.12
            _draw_block(d, lines, f, s, pad, y0, secondary)
            d.rectangle([pad, y0 - 24, pad + int(W * 0.12), y0 - 14], fill=accent)
            if subtext:
                d.text((pad, H - pad - sub_h + 10), subtext, font=_font(int(W * 0.035), font_path), fill=secondary)
        if handle and layout != "Bottom band":
            hf = _font(int(W * 0.026), font_path)
            d.text((pad, pad), handle, font=hf, fill=secondary)
        elif handle:
            hf = _font(int(W * 0.026), font_path)
            tw = d.textlength(handle, font=hf)
            d.text((W - pad - tw, H - pad * 0.5 - int(W * 0.026)), handle, font=hf, fill=accent)

    if logo_path and Path(logo_path).exists():
        logo = Image.open(logo_path).convert("RGBA")
        lw = int(W * 0.14)
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        canvas.paste(logo, (W - lw - pad, pad), logo)

    path = OUTPUT_DIR / f"post-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6:06d}.png"
    canvas.save(path, quality=95)
    return str(path)


def carousel_slide(text: str, index: int, total: int, colors: dict, size_key="4:5 (IG portrait)",
                   font_path: str = "", handle: str = "") -> str:
    """Plain text slide for carousels (tips, drop details, lookbook captions)."""
    W, H = SIZES.get(size_key, (1080, 1350))
    bg, fg, ac = _hex(colors.get("secondary", "#F2EDE4")), _hex(colors.get("primary", "#111111")), _hex(colors.get("accent", "#E4572E"))
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    pad = int(W * 0.09)
    f, lines, s = _fit_text(d, text, W - 2 * pad, H * 0.6, int(W * 0.08), font_path)
    y = (H - len(lines) * s * 1.12) / 2
    d.rectangle([pad, y - 40, pad + 90, y - 28], fill=ac)
    _draw_block(d, lines, f, s, pad, y, fg)
    sf = _font(int(W * 0.026), font_path)
    d.text((pad, H - pad), f"{index}/{total}", font=sf, fill=fg)
    if handle:
        d.text((W - pad - d.textlength(handle, font=sf), H - pad), handle, font=sf, fill=fg)
    path = OUTPUT_DIR / f"slide-{time.strftime('%Y%m%d-%H%M%S')}-{index}.png"
    img.save(path)
    return str(path)


def placeholder(colors: dict) -> Image.Image:
    """Soft brand-colour gradient for when there's no photo yet."""
    a, b = _hex(colors.get("primary", "#111111")), _hex(colors.get("accent", "#E4572E"))
    img = Image.new("RGB", (64, 64))
    for y in range(64):
        t = y / 63
        for x in range(64):
            img.putpixel((x, y), tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    return img.resize((1080, 1350)).filter(ImageFilter.GaussianBlur(4))
