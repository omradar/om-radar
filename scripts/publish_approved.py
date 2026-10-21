import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.instagram.com"
DATA = Path("data")
PENDING_FILE = DATA / "pending.json"
PUBLISHED_FILE = DATA / "published.json"


def api_post(path, values):
    body = urllib.parse.urlencode(values).encode("utf-8")
    request = urllib.request.Request(f"{API}/{path}", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Erreur API Instagram"))
    return result


def api_get(path, values):
    url = f"{API}/{path}?" + urllib.parse.urlencode(values)
    with urllib.request.urlopen(url, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Erreur API Instagram"))
    return result


def main():
    if os.environ.get("CONFIRM_PUBLISH") != "oui":
        print("Publication annulée : confirmation explicite absente.")
        sys.exit(1)

    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Le secret INSTAGRAM_ACCESS_TOKEN est absent.")

    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    url = pending.get("url", "").strip()
    title = pending.get("title", "").strip()
    filename = pending.get("filename", "").strip()
    source = pending.get("source", "OM Radar").strip()
    if not url or not title or not filename:
        raise RuntimeError("Aucun brouillon complet à publier dans data/pending.json.")
    image_path = Path("instagram-posts") / filename
    if not image_path.is_file():
        raise RuntimeError(f"Image du brouillon introuvable : {filename}")

    state = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8")) if PUBLISHED_FILE.exists() else {}
    published_urls = state.setdefault("published_urls", [])
    media_ids = state.setdefault("media_ids", [])
    if url in published_urls:
        raise RuntimeError("Cet article est déjà marqué comme publié. Publication bloquée.")

    me = api_get("me", {"fields": "user_id,username", "access_token": token})
    user_id = str(me.get("user_id", "")).strip()
    if not user_id:
        raise RuntimeError("Instagram n'a pas renvoyé d'identifiant utilisateur.")

    image_url = f"https://raw.githubusercontent.com/omradar/om-radar/main/instagram-posts/{urllib.parse.quote(filename)}"
    caption = f"{title}\n\nSource : {source}\nLire l'article : {url}\n\n#OM #OlympiqueDeMarseille #OMRadar"
    container = api_post(f"{user_id}/media", {
        "image_url": image_url,
        "caption": caption[:2200],
        "access_token": token,
    })
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError("Instagram n'a pas renvoyé d'identifiant de publication.")

    result = api_post(f"{user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    media_id = result.get("id")
    if not media_id:
        raise RuntimeError("Instagram n'a pas confirmé la publication.")

    published_urls.append(url)
    media_ids.append(str(media_id))
    PUBLISHED_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PENDING_FILE.write_text("{}\n", encoding="utf-8")
    print(f"Publication confirmée pour le compte @{me.get('username', 'Instagram')}.")
    print(f"Identifiant de publication : {media_id}")
    print("Le brouillon a été retiré de la file d'attente.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(1)
