import os, json, time
from pathlib import Path
import requests

DATA = Path("data")
PENDING_FILE = DATA / "pending.json"
STATE_FILE = DATA / "published.json"

def require(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Secret/variable manquant : {name}")
    return value

def main():
    token = require("INSTAGRAM_ACCESS_TOKEN")
    repo = require("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_REF_NAME", "main").strip()
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    if not pending.get("url") or not pending.get("filename"):
        raise SystemExit("Aucun brouillon en attente.")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {"published_urls": [], "media_ids": []}
    article_url = pending["url"]
    if article_url in state.get("published_urls", []):
        raise SystemExit("Cet article est déjà marqué comme publié : arrêt sans doublon.")

    image_url = f"https://raw.githubusercontent.com/{repo}/{branch}/instagram-posts/{pending['filename']}"
    caption = f"🔵 {pending['title']}\n\n📰 Source : {pending['source']}\n🔗 Article : {article_url}\n\n#OM #TeamOM #OlympiqueDeMarseille #OMRadar"
    base = "https://graph.instagram.com"
    session = requests.Session()
    me = session.get(f"{base}/me", params={"fields": "user_id,username", "access_token": token}, timeout=30)
    if not me.ok:
        raise SystemExit(f"Vérification du compte Instagram impossible (HTTP {me.status_code}). Vérifie le jeton et ses autorisations.")
    account = me.json()
    user_id = str(account.get("user_id", "")).strip()
    username = str(account.get("username", "")).strip()
    if not user_id:
        raise SystemExit("Instagram n'a pas retourné l'identifiant du compte.")

    response = session.post(f"{base}/{user_id}/media", data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=45)
    if not response.ok:
        raise SystemExit(f"Instagram a refusé la création du média (HTTP {response.status_code}). Vérifie les autorisations et l'image.")
    container_id = response.json().get("id")
    if not container_id:
        raise SystemExit("Instagram n'a pas retourné d'identifiant de média.")

    for _ in range(12):
        check = session.get(f"{base}/{container_id}", params={"fields": "status_code,status", "access_token": token}, timeout=30)
        if check.ok:
            status = check.json().get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise SystemExit("Instagram indique que le média ne peut pas être publié.")
        time.sleep(5)
    else:
        raise SystemExit("Instagram n'a pas terminé le traitement du visuel à temps.")

    response = session.post(f"{base}/{user_id}/media_publish", data={"creation_id": container_id, "access_token": token}, timeout=45)
    if not response.ok or not response.json().get("id"):
        raise SystemExit(f"Instagram n'a pas confirmé la publication (HTTP {response.status_code}).")
    media_id = response.json()["id"]
    urls = state.setdefault("published_urls", [])
    urls.append(article_url)
    state["published_urls"] = urls[-500:]
    state.setdefault("media_ids", []).append(media_id)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    PENDING_FILE.write_text("{}", encoding="utf-8")
    print(f"Publication confirmée pour @{username}. ID : {media_id}")

if __name__ == "__main__":
    main()
