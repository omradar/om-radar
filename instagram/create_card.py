#!/usr/bin/env python3
"""Génère une carte Instagram OM Radar dans le style éditorial approuvé.\nLe push de ce fichier déclenche un aperçu GitHub sans publier sur Instagram."""
import html
import re
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")
W = H = 1080
NAVY = (6, 20, 38)
NAVY2 = (9, 43, 75)
CYAN = (21, 188, 233)
WHITE = (248, 251, 255)
MUTED = (147, 181, 202)
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

def wrap(draw, text, f, max_width, max_lines=4):
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
# Édition spéciale du jour : carte JOUR DE MATCH pour le 22 octobre 2026.
matchday = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat() == "2026-10-22"
if matchday:
    title = "STURM GRAZ – OM : C’EST LE JOUR J"

# Fond dessiné ici : aucun texte d'exemple Canva, portrait ou statistique inventée.
im = Image.new("RGB", (W, H), NAVY)
pixels = im.load()
for y in range(H):
    t = y / (H - 1)
    for x in range(W):
        glow = max(0.0, 1 - (((x - 850) / 650) ** 2 + ((y - 340) / 650) ** 2) ** 0.5)
        pixels[x, y] = tuple(
            min(255, int(NAVY[c] * (1-t) + NAVY2[c] * t + glow * (CYAN[c] - NAVY[c]) * 0.16))
            for c in range(3)
        )

d = ImageDraw.Draw(im, "RGBA")
d.rectangle((0, 0, 12, H), fill=(*CYAN, 255))
d.polygon([(0, 0), (300, 0), (0, 300)], fill=(*CYAN, 240))
d.polygon([(0, 0), (215, 0), (0, 215)], fill=(248, 251, 255, 245))
d.polygon([(1080, 820), (820, 1080), (1080, 1080)], fill=(*CYAN, 245))
d.polygon([(1080, 880), (880, 1080), (1080, 1080)], fill=(2, 11, 23, 255))
d.rectangle((0, 0, W, H), fill=(0, 0, 0, 0))
# Grille technique discrète et anneaux de radar.
for x in range(24, W, 44):
    d.line((x, 0, x, H), fill=(53, 199, 245, 12), width=1)
for y in range(24, H, 44):
    d.line((0, y, W, y), fill=(53, 199, 245, 12), width=1)
d.arc((650, 210, 1190, 750), 20, 320, fill=(21, 188, 233, 70), width=14)
d.arc((710, 270, 1130, 690), 20, 320, fill=(248, 251, 255, 28), width=3)

logo_path = Path("assets/logo-320.png")
if logo_path.exists():
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((100, 100), Image.Resampling.LANCZOS)
    im_rgba = im.convert("RGBA")
    im_rgba.alpha_composite(logo, (65, 45))
    im = im_rgba.convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.text((180, 69), "OM RADAR", font=font(42, True), fill=WHITE)
else:
    d.text((72, 66), "OM RADAR", font=font(44, True), fill=WHITE)

d.text((180, 117), "ACTUS  ·  RÉSULTATS  ·  STATS", font=font(15, True), fill=CYAN)
d.text((1000, 78), "ÉDITION", font=font(15, True), fill=CYAN, anchor="ra")
d.text((1000, 106), "MARSEILLE", font=font(20, True), fill=WHITE, anchor="ra")
d.rounded_rectangle((72, 213, 322, 260), radius=22, fill=(*CYAN, 255))
d.text((197, 236), "JOUR DE MATCH · LIGUE EUROPA" if matchday else "LA MINUTE OM", font=font(18, True), fill=NAVY, anchor="mm")

# Titre principal provenant du site, sans inventer de score ni de chiffres.
title_font = font(66, True)
lines = wrap(d, title, title_font, 900, 4)
if len(lines) > 3:
    title_font = font(56, True)
    lines = wrap(d, title, title_font, 900, 4)
if len(lines) > 3:
    title_font = font(48, True)
    lines = wrap(d, title, title_font, 900, 4)

y = 330
line_height = title_font.size + 22
for i, line in enumerate(lines):
    color = CYAN if i == min(1, len(lines)-1) else WHITE
    d.text((72, y), line, font=title_font, fill=color, stroke_width=0)
    y += line_height

# Barre d'accent et signature de marque.
bar_y = max(640, min(y + 22, 760))
d.rounded_rectangle((76, bar_y, 86, bar_y + 100), radius=5, fill=(*CYAN, 255))
d.text((112, bar_y + 10), "CE SOIR · COUP D’ENVOI 18H45" if matchday else "L’ACTUALITÉ DE L’OLYMPIQUE", font=font(23, True), fill=WHITE)
d.text((112, bar_y + 47), "OBJECTIF : LES PREMIERS POINTS EUROPÉENS" if matchday else "DE MARSEILLE, DÉCRYPTÉE PAR OM RADAR.", font=font(18), fill=MUTED)
d.line((72, 875, 1008, 875), fill=(21, 188, 233, 150), width=2)
d.text((72, 910), "UN CLUB. UNE VILLE. UNE PASSION.", font=font(20, True), fill=CYAN)
d.text((72, 963), "OMRADAR.GITHUB.IO/OM-RADAR", font=font(17), fill=MUTED)
d.text((1008, 965), "#OMRADAR", font=font(24, True), fill=WHITE, anchor="ra")

OUT.parent.mkdir(parents=True, exist_ok=True)
im.save(OUT, "JPEG", quality=95, optimize=True)
print("APERÇU UNIQUEMENT — aucune publication Instagram déclenchée.")
print("Carte OM Radar générée :", OUT, "| titre :", title[:160])
