import os, json, re, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
import feedparser
from PIL import Image, ImageDraw, ImageFont

DATA = Path("data")
POSTS = Path("instagram-posts")
DATA.mkdir(exist_ok=True)
POSTS.mkdir(exist_ok=True)
STATE_FILE = DATA / "published.json"
PENDING_FILE = DATA / "pending.json"
REJECTED_FILE = DATA / "rejected.json"
FEED_URL = "https://news.google.com/rss/search?q=" + quote_plus("Olympique de Marseille when:2d") + "&hl=fr&gl=FR&ceid=FR:fr"
MAX_AGE_HOURS = 48

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def get_font(size, bold=False):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size) if Path(path).exists() else ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = re.sub(r"\s+", " ", text).strip().split()
    lines, current = [], ""
    for word in words:
        candidate = word if not current else current + " " + word
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def make_image(title, source, output):
    size = 1080
    image = Image.new("RGB", (size, size), "#071426")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, size), fill="#20B8E6")
    draw.polygon([(770, 0), (1080, 0), (1080, 310), (950, 250)], fill="#0A2D4B")
    draw.arc((690, 80, 1190, 580), 25, 320, fill="#167DA8", width=10)
    draw.arc((760, 145, 1120, 505), 25, 320, fill="#104A70", width=5)

    logo_path = Path("assets/logo-320.png")
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((118, 118), Image.Resampling.LANCZOS)
        rgba = image.convert("RGBA")
        rgba.alpha_composite(logo, (58, 42))
        image = rgba.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.text((198, 68), "OM RADAR", font=get_font(42, True), fill="white")
    else:
        draw.text((64, 66), "OM RADAR", font=get_font(46, True), fill="white")

    draw.text((64, 175), "ACTUALITÉ OM", font=get_font(25, True), fill="#20B8E6")
    draw.line((64, 222, 1016, 222), fill="#167DA8", width=3)
    draw.rounded_rectangle((48, 270, 1032, 820), radius=28, fill="#061322", outline="#145879", width=2)
    draw.rounded_rectangle((76, 310, 88, 770), radius=6, fill="#20B8E6")

    title_font = get_font(58, True)
    lines = wrap_text(draw, title, title_font, 870)
    if len(lines) > 6:
        title_font = get_font(48, True)
        lines = wrap_text(draw, title, title_font, 870)
    if len(lines) > 6:
        lines = lines[:6]
        lines[-1] = lines[-1].rstrip(" ,;:.") + "…"
    y = 325
    for line in lines:
        draw.text((120, y), line, font=title_font, fill="white")
        y += 68

    draw.line((64, 865, 1016, 865), fill="#29445F", width=3)
    draw.text((64, 890), "SOURCE : " + (source[:55] if source else "ACTUALITÉ"), font=get_font(22, True), fill="#B8C9D9")
    draw.text((64, 970), "OM RADAR  •  ACTUALITÉS & ANALYSES", font=get_font(22, True), fill="#20B8E6")
    image.save(output, "JPEG", quality=92, optimize=True)

def main():
    state = load_json(STATE_FILE, {"published_urls": [], "media_ids": []})
    published = set(state.get("published_urls", []))
    pending = load_json(PENDING_FILE, {})
    rejected = set(load_json(REJECTED_FILE, {}).get("rejected_urls", []))
    if pending.get("url") and pending["url"] not in published and pending["url"] not in rejected:
        print("Un brouillon attend déjà une validation : " + str(pending.get("filename", "")))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("ready=true\n")
        return

    feed = feedparser.parse(FEED_URL)
    if not feed.entries:
        print("Aucun article dans le flux RSS. Aucun brouillon créé.")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("ready=false\n")
        return

    now = datetime.now(timezone.utc)
    candidates = []
    for entry in feed.entries:
        url = entry.get("link", "").strip()
        title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
        if not url or not title or url in published or url in rejected:
            continue
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if published_parsed:
            from calendar import timegm
            dt = datetime.fromtimestamp(timegm(published_parsed), timezone.utc)
            if now - dt > timedelta(hours=MAX_AGE_HOURS):
                continue
        source = ""
        if entry.get("source") and isinstance(entry.source, dict):
            source = entry.source.get("title", "")
        if " - " in title:
            title, inferred_source = title.rsplit(" - ", 1)
            source = source or inferred_source
        candidates.append((title, source, url))
    if not candidates:
        print("Aucun article inédit assez récent. Aucun brouillon créé.")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("ready=false\n")
        return

    title, source, url = candidates[0]
    title = title[:180]
    short_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    filename = f"om-radar-{now.strftime('%Y%m%d')}-{short_hash}.jpg"
    make_image(title, source or "Source liée", POSTS / filename)
    pending = {"url": url, "title": title, "source": source or "Source liée", "filename": filename, "prepared_at": now.isoformat()}
    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("ready=true\n")
    print(f"Brouillon prêt : {filename}")
    print(f"Titre : {title}")
    print(f"Source : {source}")
    print(f"URL article : {url}")

if __name__ == "__main__":
    main()
