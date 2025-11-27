# autoposter_bp2.py
from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

FEED_AT_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaamoypyhyi3y"
HOURS_BACK = 1
MAX_PER_RUN = 100
MAX_PER_USER = 2
DELAY_SECONDS = 2
REPOST_LOG_FILE = "reposted_bp2.txt"  # apart bestand voor deze versie

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    print(f"{ts} {msg}")

def parse_created_dt(record, post):
    for attr in ("createdAt", "indexedAt", "created_at", "timestamp"):
        val = getattr(record, attr, None) or getattr(post, attr, None)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except:
                pass
    return None

def main():
    username = os.getenv("BSKY_USERNAME_BP")
    password = os.getenv("BSKY_PASSWORD_BP")
    if not username or not password:
        log("❌ Geen BSKY_USERNAME_BP / BSKY_PASSWORD_BP gezet.")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    done = set()
    if os.path.exists(REPOST_LOG_FILE):
        with open(REPOST_LOG_FILE, "r") as f:
            done = set(line.strip() for line in f if line.strip())

    try:
        log("📥 Feed ophalen...")
        feed_data = client.app.bsky.feed.get_feed({"feed": FEED_AT_URI, "limit": 100}).feed
        log(f"📊 {len(feed_data)} totaal in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    per_user = {}
    posts = []

    for item in feed_data:
        post = item.post
        uri = post.uri
        record = post.record

        if getattr(item, "reason", None):
            continue
        if getattr(record, "reply", None):
            continue
        if uri in done:
            continue

        created = parse_created_dt(record, post)
        if not created or created < cutoff:
            continue

        author = getattr(post.author, "did", None)
        posts.append({"uri": uri, "cid": post.cid, "author": author, "created": created})

    posts.sort(key=lambda x: x["created"])

    filtered = []
    for p in posts:
        if len(filtered) >= MAX_PER_RUN:
            break
        if per_user.get(p["author"], 0) >= MAX_PER_USER:
            continue
        per_user[p["author"]] = per_user.get(p["author"], 0) + 1
        filtered.append(p)

    log(f"🧩 {len(filtered)} posts geselecteerd.")
    reposted = liked = 0

    for p in filtered:
        try:
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={"$type": "app.bsky.feed.repost", "subject": {"uri": p["uri"], "cid": p["cid"]}, "createdAt": now_utc_iso()},
            )
            reposted += 1
            done.add(p["uri"])

            try:
                client.app.bsky.feed.like.create(
                    repo=client.me.did,
                    record={"$type": "app.bsky.feed.like", "subject": {"uri": p["uri"], "cid": p["cid"]}, "createdAt": now_utc_iso()},
                )
                liked += 1
            except:
                pass

            time.sleep(DELAY_SECONDS)

        except:
            pass

    with open(REPOST_LOG_FILE, "w") as f:
        f.write("\n".join(done))

    log(f"✅ Klaar — {reposted} reposts uitgevoerd ({liked} geliked).")

if __name__ == "__main__":
    main()