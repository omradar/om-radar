"""Tests hors connexion de la récupération des actualités : python tests/test_news.py"""
import base64
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

spec = importlib.util.spec_from_file_location("build", Path(__file__).resolve().parent.parent / "build.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

ok = True


def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(("OK   " if good else "ECHEC"), name, "" if good else f"\n   obtenu : {got!r}\n   attendu : {want!r}")


# --- noms de médias propres
check("source URL brute", b.pretty_source("https://www.433foot.fr/"), "433 Foot")
check("source nom de domaine", b.pretty_source("footmercato.net"), "Foot Mercato")
check("source domaine inconnu", b.pretty_source("exemple-presse.fr"), "Exemple-presse")
check("source déjà propre", b.pretty_source("Le Phocéen"), "Le Phocéen")

# --- images en https
check("http vers https", b.https_url("http://x.fr/a.jpg"), "https://x.fr/a.jpg")
check("protocole relatif", b.https_url("//x.fr/a.jpg"), "https://x.fr/a.jpg")
check("pas une URL", b.https_url("data:image/png;base64,AAA"), "")

# --- identifiant Google (ancien format) : l'adresse est dans l'identifiant
url = "https://www.sport.fr/football/om-exemple-123.shtml"
raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
tok = base64.urlsafe_b64encode(raw).decode().rstrip("=")
check("décodage ancien format Google", b.gn_legacy(tok), url)
check("nouveau format (pas de décodage local)", b.gn_legacy("CBMiAU_yqLPexemple"), "")
check("jeton extrait du lien", b.gn_token("https://news.google.com/rss/articles/" + tok + "?oc=5"), tok)
check("lien non Google", b.gn_token("https://exemple.fr/articles/abc"), "")

# --- réponse du serveur Google
inner = json.dumps(["garturlres", "https://www.footmercato.net/om/article-1.html", 1])
reply = ")]}'\n\n" + json.dumps([["wrb.fr", "Fbv4je", inner, None, None, None, "generic"], ["di", 12], ["af.httprm", 12, "x", 5]])
check("réponse Google", b.gn_parse_reply(reply), "https://www.footmercato.net/om/article-1.html")
check("réponse invalide", b.gn_parse_reply("n'importe quoi"), "")

# --- flux RSS avec image dans media:content, enclosure, ou <img>
rss = """<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>OM : titre un</title><link>https://a.fr/1</link><pubDate>Mon, 19 Oct 2026 21:00:00 +0000</pubDate>
<description>Un long extrait de l'article numéro un sur l'OM, pour tester la coupe du texte à la bonne longueur.</description>
<media:content url="http://img.a.fr/1.jpg" medium="image"/></item>
<item><title>OM : titre deux</title><link>https://a.fr/2</link><enclosure url="https://img.a.fr/2.jpg" type="image/jpeg"/></item>
<item><title>OM : titre trois</title><link>https://a.fr/3</link><content:encoded><![CDATA[<p><img src="//img.a.fr/3.jpg"></p>texte]]></content:encoded></item>
<item><title>Autre sport</title><link>https://a.fr/4</link><description>Tennis</description></item>
</channel></rss>""".encode()
got = b.parse_feed(rss, {"name": "Test", "category": "auto", "only_om": True})
check("filtre OM", [g["title"] for g in got], ["OM : titre un", "OM : titre deux", "OM : titre trois"])
check("image media:content (http vers https)", got[0]["image"], "https://img.a.fr/1.jpg")
check("image enclosure", got[1]["image"], "https://img.a.fr/2.jpg")
check("image dans le texte", got[2]["image"], "https://img.a.fr/3.jpg")

# --- flux Google : source propre, pas de résumé, pas d'image
g = """<rss><channel><item><title>Titre exemple - 433foot.fr</title><link>https://news.google.com/rss/articles/CBMiXYZ</link>
<source url="https://www.433foot.fr">https://www.433foot.fr/</source><pubDate>Tue, 20 Oct 2026 06:00:00 GMT</pubDate><description>x</description></item></channel></rss>""".encode()
got = b.parse_feed(g, {"name": "Google", "kind": "google", "category": "Actualités"})
check("Google : titre sans nom de média", got[0]["title"], "Titre exemple")
check("Google : nom de média propre", got[0]["source"], "433 Foot")

# --- image de partage d'une page
page = '<html><head><meta property="og:image" content="http://cdn.a.fr/x.jpg?w=1200&amp;h=630"></head></html>'
b.http_get = lambda *a, **k: page.encode()
check("og:image", b.og_image("https://a.fr/x"), "https://cdn.a.fr/x.jpg?w=1200&h=630")
b.http_get = lambda *a, **k: b'<meta content="https://cdn.a.fr/t.jpg" name="twitter:image">'
check("twitter:image (attributs inversés)", b.og_image("https://a.fr/x"), "https://cdn.a.fr/t.jpg")

print("\nTous les tests passent." if ok else "\nDes tests échouent.")
sys.exit(0 if ok else 1)
