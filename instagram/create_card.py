#!/usr/bin/env python3
"""Génère une carte Instagram OM Radar graphique, sans photos de personnes."""
import html
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")
W = H = 1080
NAVY = (5, 17, 36)
NAVY2 = (7, 35, 62)
CYAN = (60, 180, 242)
WHITE = (248, 251, 255)
UA = {"User-Agent": "Mozilla/5.0 (compatible; OM-Radar-Instagram/1.0)"}

class FeaturedTitle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_hero = False
        self.in_heading = False
        self.parts = []
        self.title = ""
    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "article" and "slide" in classes and "hero" in classes:
            self.in_hero = True
        if self.in_hero and tag in ("h1", "h2"):
            self.in_heading = True
            self.parts = []
    def handle_data(self, data):
        if self.in_hero and self.in_heading:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if self.in_hero and tag in ("h1", "h2") and self.in_heading:
            self.title = re.sub(r"\s+", " ", html.unescape(" ".join(self.parts))).strip()
            self.in_heading = False
        elif tag == "article" and self.in_hero:
            self.in_hero = False

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

def wrap(draw, text, f, max_width, max_lines=5):
    words, lines, line = text.split(), [], ""
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
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=f)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last.rstrip(" ,;:.") + "…"
    return lines

req = urllib.request.Request(SITE, headers=UA)
with urllib.request.urlopen(req, timeout=20) as response:
    page_html = response.read().decode("utf-8", "replace")
parser = FeaturedTitle()
parser.feed(page_html)
title = parser.title or "L’actualité de l’Olympique de Marseille"
title = re.sub(r"\s+", " ", title).strip()

# Fond bleu nuit texturé avec accents graphiques abstraits, sans photo ni portrait.
im = Image.new("RGB", (W, H), NAVY)
px = im.load()
for y in range(H):
    t = y / (H - 1)
    row = tuple(int(NAVY[i] * (1-t) + NAVY2[i] * t) for i in range(3))
    for x in range(W):
        glow = max(0.0, 1 - (((x-900)/650)**2 + ((y-180)/500)**2)**0.5)
        px[x, y] = tuple(min(255, int(row[i] + glow * (CYAN[i]-row[i]) * 0.16)) for i in range(3))

d = ImageDraw.Draw(im, "RGBA")
# Traits obliques et grand motif circulaire discret.
d.arc((570, 170, 1230, 830), 30, 320, fill=(*CYAN, 45), width=16)
d.arc((640, 240, 1160, 760), 30, 320, fill=(*CYAN, 28), width=7)
for k in range(4):
    d.polygon([(820+k*48, 0), (875+k*48, 0), (500+k*48, 400), (465+k*48, 400)], fill=(*CYAN, 18))
d.polygon([(0, 970), (210, 970), (100, 1080), (0, 1080)], fill=(*CYAN, 210))
d.polygon([(0, 1020), (120, 1020), (60, 1080), (0, 1080)], fill=(255,255,255,230))

# Logo existant du site : conserve son alpha s'il est présent.
logo_path = Path("assets/logo-320.png")
if logo_path.exists():
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((142, 142), Image.Resampling.LANCZOS)
    im_rgba = im.convert("RGBA")
    im_rgba.alpha_composite(logo, (62, 46))
    im = im_rgba.convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.text((225, 67), "OM RADAR", font=font(40, True), fill=WHITE)
else:
    d.rounded_rectangle((58, 55, 425, 145), radius=20, fill=(3, 16, 30, 230))
    d.text((85, 73), "OM RADAR", font=font(42, True), fill=WHITE)

d.text((64, 190), "LE POINT SUR L’OM", font=font(23, True), fill=CYAN)
d.line((64, 235, 1016, 235), fill=(*CYAN, 160), width=3)
d.text((64, 285), "ACTUALITÉ", font=font(21, True), fill=CYAN)
d.rounded_rectangle((48, 340, 1032, 870), radius=28, fill=(3, 14, 29, 224), outline=(*CYAN, 115), width=2)
d.rounded_rectangle((82, 385, 95, 805), radius=6, fill=(*CYAN, 255))
f_title = font(51, True)
lines = wrap(d, title, f_title, 850, 5)
y = 410
for line in lines:
    d.text((125, y), line, font=f_title, fill=WHITE, stroke_width=0)
    y += 77
d.line((125, 815, 955, 815), fill=(*CYAN, 200), width=2)
d.text((64, 920), "ACTUALITÉS  •  RÉSULTATS  •  ANALYSES", font=font(22, True), fill=CYAN)
d.text((64, 1010), "omradar.github.io/om-radar", font=font(19), fill=(220,235,247,220))

OUT.parent.mkdir(parents=True, exist_ok=True)
im.save(OUT, "JPEG", quality=94, optimize=True)
print("Brouillon créé :", OUT, "| titre :", title[:160])
