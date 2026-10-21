#!/usr/bin/env python3
"""Génère une carte Instagram éditoriale OM Radar, sans photos de personnes."""
import html
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")
W = H = 1080
NAVY = (4, 14, 31)
NAVY2 = (7, 31, 57)
CYAN = (48, 190, 239)
WHITE = (247, 250, 255)
MUTED = (166, 190, 211)
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
title = re.sub(r"\s+", " ", parser.title or "L’actualité de l’Olympique de Marseille").strip()

# Utilise les deux modèles Canva comme base visuelle quand ils sont présents.
# Le panneau éditorial opaque plus bas masque le texte d'exemple du modèle.
from PIL import ImageOps
is_stat = bool(re.search(r"\d|%|\b(chiffre|statistique|pourcentage|classement)\b", title, re.I))
template_path = Path(
    "instagram/Post Instagram carré OM Radar — Chiffre du jour.png"
    if is_stat else "instagram/Carte actu OM Radar.png"
)
if template_path.exists():
    im = ImageOps.fit(Image.open(template_path).convert("RGB"), (W, H), method=Image.Resampling.LANCZOS)
else:
    # Repli autonome si un modèle est absent.
    im = Image.new("RGB", (W, H), NAVY)
    px = im.load()
    for y0 in range(H):
        t = y0 / (H - 1)
        row = tuple(int(NAVY[i] * (1-t) + NAVY2[i] * t) for i in range(3))
        for x in range(W):
            glow = max(0.0, 1 - (((x-900)/720)**2 + ((y0-210)/560)**2)**0.5)
            px[x, y0] = tuple(min(255, int(row[i] + glow * (CYAN[i]-row[i]) * 0.13)) for i in range(3))

d = ImageDraw.Draw(im, "RGBA")
# Motif circulaire discret, lignes obliques et liseré de signature.
d.rectangle((0, 0, 14, H), fill=(*CYAN, 255))
d.arc((680, 105, 1250, 675), 25, 325, fill=(*CYAN, 50), width=18)
d.arc((745, 170, 1185, 610), 25, 325, fill=(255, 255, 255, 24), width=3)
for k in range(5):
    d.polygon([(870+k*45, 0), (900+k*45, 0), (600+k*45, 300), (570+k*45, 300)], fill=(*CYAN, 13))
d.polygon([(0, 1000), (185, 1000), (105, 1080), (0, 1080)], fill=(*CYAN, 230))
d.polygon([(0, 1035), (92, 1035), (47, 1080), (0, 1080)], fill=(255, 255, 255, 235))

# Logo du projet, sans portrait ni photo d'article.
logo_path = Path("assets/logo-320.png")
if logo_path.exists():
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((112, 112), Image.Resampling.LANCZOS)
    im_rgba = im.convert("RGBA")
    im_rgba.alpha_composite(logo, (58, 42))
    im = im_rgba.convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.text((190, 66), "OM RADAR", font=font(37, True), fill=WHITE)
else:
    d.text((64, 67), "OM RADAR", font=font(40, True), fill=WHITE)

d.text((64, 177), "L’ACTU MARSEILLAISE, SANS DÉTOUR", font=font(19, True), fill=CYAN)
d.line((64, 220, 1016, 220), fill=(*CYAN, 115), width=2)
d.rounded_rectangle((64, 257, 267, 303), radius=22, fill=(*CYAN, 28), outline=(*CYAN, 175), width=2)
d.text((84, 269), "LE POINT OM", font=font(17, True), fill=CYAN)

# Grand bloc éditorial, respirant et lisible en petit dans le fil Instagram.
d.rounded_rectangle((48, 330, 1032, 860), radius=30, fill=(3, 12, 27, 252), outline=(255, 255, 255, 80), width=2)
d.rounded_rectangle((82, 382, 92, 796), radius=5, fill=(*CYAN, 255))
title_font = font(52, True)
lines = wrap(d, title, title_font, 850, 5)
if len(lines) >= 5 and any(len(line) > 24 for line in lines):
    title_font = font(46, True)
    lines = wrap(d, title, title_font, 850, 5)
line_height = 74 if title_font.size >= 50 else 66
y = 392
for line in lines:
    d.text((125, y), line, font=title_font, fill=WHITE)
    y += line_height

# Pied de carte de marque.
d.line((64, 900, 1016, 900), fill=(255, 255, 255, 45), width=2)
d.text((64, 928), "ACTUALITÉS  /  RÉSULTATS  /  STATS", font=font(20, True), fill=CYAN)
d.text((64, 982), "OMRADAR.GITHUB.IO/OM-RADAR", font=font(17), fill=MUTED)
d.text((930, 978), "OM", font=font(40, True), fill=(255, 255, 255, 45))

OUT.parent.mkdir(parents=True, exist_ok=True)
im.save(OUT, "JPEG", quality=95, optimize=True)
print("Carte OM Radar générée :", OUT, "| titre :", title[:160])
