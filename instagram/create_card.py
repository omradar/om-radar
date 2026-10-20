#!/usr/bin/env python3
"""Crée une carte OM Radar originale depuis les informations publiques du site."""
import html
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from PIL import Image, ImageDraw, ImageFont

SITE = "https://omradar.github.io/om-radar/"
OUT = Path("instagram/latest.jpg")
PARIS = ZoneInfo("Europe/Paris")

class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture_h1 = False
        self.capture_result = False
        self.capture_club = False
        self.capture_me = False
        self.headlines = []
        self.headline = ""
        self.result = ""
        self.clubs = []
        self.club = ""
        self.me_cells = []
        self.cell = ""
        self.in_me_cell = False
        self.in_row = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = a.get("class", "").split()
        if tag == "h1" and "slide" not in classes:
            self.capture_h1 = True
            self.headline = ""
        if "result" in classes:
            self.capture_result = True
            self.result = ""
        if "club" in classes:
            self.capture_club = True
            self.club = ""
        if tag == "tr" and "me" in classes:
            self.in_row = True
            self.me_cells = []
        if self.in_row and tag == "td":
            self.in_me_cell = True
            self.cell = ""

    def handle_endtag(self, tag):
        if tag == "h1" and self.capture_h1:
            self.capture_h1 = False
            text = clean(self.headline)
            if text and text not in self.headlines:
                self.headlines.append(text)
        if tag == "span" and self.capture_result:
            self.capture_result = False
            self.result = clean(self.result)
        if tag == "span" and self.capture_club:
            self.capture_club = False
            name = clean(self.club)
            if name:
                self.clubs.append(name)
        if tag == "td" and self.in_me_cell:
            self.in_me_cell = False
            self.me_cells.append(clean(self.cell))
        if tag == "tr" and self.in_row:
            self.in_row = False

    def handle_data(self, data):
        if self.capture_h1:
            self.headline += " " + data
        if self.capture_result:
            self.result += " " + data
        if self.capture_club:
            self.club += " " + data
        if self.in_me_cell:
            self.cell += " " + data

def clean(value):
    return re.sub(r"\\s+", " ", html.unescape(value or "")).strip()

req = urllib.request.Request(SITE, headers={"User-Agent": "OM-Radar-Instagram/1.0"})
with urllib.request.urlopen(req, timeout=20) as response:
    page = response.read().decode("utf-8", "replace")
parser = SiteParser()
parser.feed(page)

# À 10 h : actualité. À 20 h : résultat et chiffres du classement.
hour = datetime.now(PARIS).hour
if 15 <= hour < 23:
    kind = "RÉSULTATS & STATS"
    title = ""
    # Le site présente le dernier score avec les noms des équipes.
    match = re.search(r'<div class="scoreboard">.*?</div>.*?<div class="meta">', page, re.S)
    if match:
        block = match.group(0)
        clubs = [clean(x) for x in re.findall(r'<div class="club">.*?<span>(.*?)</span>', block, re.S)]
        score = re.search(r'<div class="result num">([^<]+)</div>', block)
        if clubs and score:
            title = f"{clubs[0]} {clean(score.group(1))} {clubs[-1]}"
    row = re.search(r'<tr class="me">(.*?)</tr>', page, re.S)
    if row:
        cells = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.S)]
        if len(cells) >= 4:
            pos = re.sub(r"<.*?>", "", cells[0])
            pts = re.sub(r"<.*?>", "", cells[2])
            played = re.sub(r"<.*?>", "", cells[3])
            statline = f"Ligue 1 : {pos}e · {pts} points · {played} matchs"
        else:
            statline = "Classement Ligue 1 sur OM Radar"
    else:
        statline = "Classement Ligue 1 sur OM Radar"
    if not title:
        title = "Le dernier résultat de l'OM"
    subtitle = statline
else:
    kind = "ACTUALITÉ DU JOUR"
    title = parser.headlines[0] if parser.headlines else "Toute l'actualité de l'Olympique de Marseille"
    subtitle = "L'essentiel de l'OM, sur OM Radar"

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
draw.text((76, 160), kind, font=font(28, True), fill="#58BCEB")

f = font(56 if kind == "ACTUALITÉ DU JOUR" else 64, True)
lines, line = [], ""
for word in title.split():
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

# Bandeau secondaire avec une information complémentaire, sans inventer de chiffres.
draw.rounded_rectangle((72, 800, 1008, 974), radius=24, fill="#58BCEB")
subfont = font(27, True)
words, sublines, line = subtitle.split(), [], ""
for word in words:
    candidate = (line + " " + word).strip()
    if draw.textbbox((0, 0), candidate, font=subfont)[2] <= 850:
        line = candidate
    else:
        if line:
            sublines.append(line)
        line = word
if line:
    sublines.append(line)
for i, part in enumerate(sublines[:3]):
    draw.text((104, 845 + i * 38), part, font=subfont, fill="#0B1F33")

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "JPEG", quality=92, optimize=True)
print("Carte préparée :", kind, "|", title)
