#!/usr/bin/env python3
"""Prépare une carte Instagram originale à partir du titre à la une du site OM Radar."""
import html
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")

class HeadlineParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h1 = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "h1":
            self.in_h1 = True
    def handle_endtag(self, tag):
        if tag.lower() == "h1":
            self.in_h1 = False
    def handle_data(self, data):
        if self.in_h1:
            text = data.strip()
            if text:
                self.parts.append(text)

req = urllib.request.Request(SITE, headers={"User-Agent": "OM-Radar-Instagram/1.0"})
with urllib.request.urlopen(req, timeout=20) as response:
    page = response.read().decode("utf-8", "replace")
parser = HeadlineParser()
parser.feed(page)
title = re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
if not title:
    title = "Toute l'actualité de l'Olympique de Marseille"

W, H = 1080, 1080
img = Image.new("RGB", (W, H), "#0B1F33")
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, W, 18), fill="#58BCEB")
draw.ellipse((710, 100, 1200, 590), fill="#123B5D")
draw.ellipse((820, 210, 1110, 500), outline="#58BCEB", width=8)

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

draw.text((72, 80), "OM RADAR", font=font(54, True), fill="#FFFFFF")
draw.text((76, 160), "ACTUALITÉS  •  RÉSULTATS  •  STATS", font=font(24, True), fill="#58BCEB")

# Wrap the headline into readable lines, keeping it within the square.
f = font(58, True)
words = title.split()
lines, line = [], ""
for word in words:
    candidate = (line + " " + word).strip()
    if draw.textbbox((0, 0), candidate, font=f)[2] <= 900:
        line = candidate
    else:
        if line:
            lines.append(line)
        line = word
if line:
    lines.append(line)
if len(lines) > 7:
    lines = lines[:6] + ["…"]
y = 350
for part in lines:
    draw.text((76, y), part, font=f, fill="#FFFFFF")
    y += 76

draw.rounded_rectangle((72, 870, 1008, 974), radius=24, fill="#58BCEB")
draw.text((104, 900), "À retrouver sur omradar.github.io", font=font(28, True), fill="#0B1F33")
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "JPEG", quality=92, optimize=True)
print("Carte préparée pour le titre :", title)
