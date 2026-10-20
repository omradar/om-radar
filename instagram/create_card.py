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

class FeaturedTitle(HTMLParser):
    """Lit le titre de la une, sans télécharger ni réutiliser les images."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_featured = False
        self.in_h1 = False
        self.title = ""
        self.parts = []
    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "article" and "slide" in classes and "hero" in classes:
            self.in_featured = True
        if self.in_featured and tag == "h1":
            self.in_h1 = True
            self.parts = []
    def handle_data(self, data):
        if self.in_featured and self.in_h1:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if self.in_featured and tag == "h1" and self.in_h1:
            self.title = clean(" ".join(self.parts))
            self.in_h1 = False
        elif self.in_featured and tag == "article":
            self.in_featured = False


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

req = urllib.request.Request(SITE, headers={"User-Agent": "Mozilla/5.0 (compatible; OM-Radar-Instagram/1.0)"})
with urllib.request.urlopen(req, timeout=20) as response:
    page_html = response.read().decode("utf-8", "replace")
parser = FeaturedTitle()
parser.feed(page_html)
title = parser.title or "L’actualité de l’Olympique de Marseille"
title = re.sub(r"\\s+", " ", title).strip()

# Carte graphique originale : aucune photo de personne ni image d'article.
im = Image.new("RGB", (W, H))
pixels = im.load()
for y in range(H):
    t = y / (H - 1)
    base = tuple(int(NAVY[i] * (1 - t) + (10, 53, 82)[i] * t) for i in range(3))
    for x in range(W):
        glow = max(0.0, 1.0 - (((x - 850) / 620) ** 2 + ((y - 160) / 500) ** 2) ** 0.5)
        pixels[x, y] = tuple(min(255, int(base[i] + glow * max(0, CYAN[i] - base[i]) * 0.22)) for i in range(3))

draw = ImageDraw.Draw(im, "RGBA")
# Motif abstrait de terrain de football.
draw.rounded_rectangle((125, 230, 955, 1060), radius=390, outline=(88, 188, 235, 42), width=4)
draw.ellipse((325, 430, 755, 860), outline=(88, 188, 235, 38), width=4)
draw.line((540, 270, 540, 1020), fill=(88, 188, 235, 32), width=4)
draw.rounded_rectangle((285, 255, 795, 430), radius=10, outline=(88, 188, 235, 30), width=4)
draw.rounded_rectangle((285, 865, 795, 1040), radius=10, outline=(88, 188, 235, 30), width=4)

draw.rounded_rectangle((58, 55, 430, 145), radius=22, fill=(3, 16, 30, 225))
draw.rounded_rectangle((58, 55, 72, 145), radius=7, fill=CYAN + (255,))
draw.text((98, 73), "OM RADAR", font=font(42, True), fill=(255,255,255,255))
draw.text((62, 190), "LE POINT SUR L’OM", font=font(23, True), fill=CYAN + (255,))
draw.rounded_rectangle((48, 490, 1032, 965), radius=30, fill=(3, 16, 30, 232), outline=(88, 188, 235, 100), width=2)
draw.rounded_rectangle((82, 535, 94, 885), radius=6, fill=CYAN + (255,))
f_title = font(49, True)
lines = wrap(draw, title, f_title, 850, 5)
y = 548
for line in lines:
    draw.text((124, y), line, font=f_title, fill=(255,255,255,255))
    y += 66
draw.line((124, 890, 955, 890), fill=(88, 188, 235, 210), width=2)
draw.text((124, 914), "ACTUALITÉS • RÉSULTATS • ANALYSES", font=font(19, True), fill=CYAN + (255,))
draw.text((62, 1015), "omradar.github.io/om-radar", font=font(18), fill=(225,238,248,210))

OUT.parent.mkdir(parents=True, exist_ok=True)
photo.convert("RGB").save(OUT, "JPEG", quality=93, optimize=True)
print("Brouillon préparé :", short)
