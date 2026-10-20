#!/usr/bin/env python3
"""Prépare une carte Instagram photo-first pour OM Radar. Brouillon uniquement, aucune publication automatique."""
import html
import io
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")
W = H = 1080
CYAN = "#58BCEB"
NAVY = "#071827"
UA = {"User-Agent": "Mozilla/5.0 (compatible; OM-Radar-Instagram/1.0)"}

def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def extract_featured(page_html):
    """Titre et photo extraits du même bloc vedette ; jamais d'image choisie au hasard."""
    blocks = re.findall(
        r'<article\\b(?=[^>]*class=["\\'][^"\\']*\\bslide\\b[^"\\']*\\bhero\\b[^"\\']*["\\'])[^>]*>(.*?)</article>',
        page_html, re.I | re.S
    )
    for block in blocks:
        heading = re.search(r'<h1\\b[^>]*>(.*?)</h1>', block, re.I | re.S)
        image = re.search(r'<img\\b(?=[^>]*class=["\\'][^"\\']*\\bbg\\b[^"\\']*["\\'])[^>]*>', block, re.I | re.S)
        if not heading or not image:
            continue
        title = clean(heading.group(1))
        src = re.search(r'\\bsrc=["\\']([^"\\']+)["\\']', image.group(0), re.I)
        if title and src:
            return title, urllib.parse.urljoin(SITE, html.unescape(src.group(1)))
    return "", ""


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(3_000_000)

def wrap(draw, text, f, max_width, max_lines=4):
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=f)[2] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=f)[2] > max_width:
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] = lines[-1].rstrip(" ,;:.") + "…"
    return lines

req = urllib.request.Request(SITE, headers=UA)
with urllib.request.urlopen(req, timeout=20) as response:
    page_html = response.read().decode("utf-8", "replace")
title, image_url = extract_featured(page_html)
if not title or not image_url:
    raise SystemExit("Impossible d'associer avec certitude le titre et la photo de la même actualité : aucune carte générée.")

title = re.sub(r"\\s+", " ", title).strip()
# Un titre éditorial court donne une carte lisible, sans déformer l'information.
if len(title) > 112:
    short = title[:109].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
else:
    short = title

try:
    raw = fetch(image_url)
    photo = Image.open(io.BytesIO(raw)).convert("RGB")
    if photo.width < 300 or photo.height < 180:
        raise ValueError("photo trop petite")
except Exception as exc:
    raise SystemExit("La photo associée à l'actualité n'est pas exploitable : carte non générée.") from exc

# Recadrage carré centré, puis léger flou uniquement sous le voile pour un rendu éditorial.
ratio = max(W / photo.width, H / photo.height)
photo = photo.resize((int(photo.width * ratio), int(photo.height * ratio)), Image.Resampling.LANCZOS)
left = (photo.width - W) // 2
top = (photo.height - H) // 2
photo = photo.crop((left, top, left + W, top + H)).convert("RGBA")

overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
pix = overlay.load()
for y in range(H):
    # Photo lisible en haut, dégradé sombre sous le titre.
    alpha = int(28 + 205 * max(0, min(1, (y - 280) / 620)) ** 1.35)
    for x in range(W):
        pix[x, y] = (4, 17, 29, alpha)
photo = Image.alpha_composite(photo, overlay)
draw = ImageDraw.Draw(photo)

# Identité de marque sobre, en haut.
draw.rounded_rectangle((56, 52, 390, 132), radius=18, fill=(5, 22, 36, 205))
draw.rounded_rectangle((56, 52, 68, 132), radius=5, fill=CYAN)
draw.text((90, 66), "OM RADAR", font=font(37, True), fill="white")
draw.text((62, 178), "ACTUALITÉ OM  •  LE POINT", font=font(22, True), fill=CYAN)

# Panneau sombre translucide au bas de la photo.
draw.rounded_rectangle((48, 610, 1032, 1015), radius=28, fill=(4, 17, 29, 222))
draw.rounded_rectangle((80, 650, 91, 965), radius=5, fill=CYAN)
f = font(48, True)
lines = wrap(draw, short, f, 850, 4)
y = 650
for line in lines:
    draw.text((120, y), line, font=f, fill="white", stroke_width=0)
    y += 66

draw.line((120, 934, 970, 934), fill=(88, 188, 235, 190), width=2)
draw.text((120, 953), "À RETROUVER SUR OM RADAR", font=font(20, True), fill=CYAN)

OUT.parent.mkdir(parents=True, exist_ok=True)
photo.convert("RGB").save(OUT, "JPEG", quality=93, optimize=True)
print("Brouillon préparé :", short)
