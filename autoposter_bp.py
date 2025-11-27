# autoposter_bp.py
from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

# === SETTINGS ===
FEED_AT_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaae6jfc5w2oi"
HOURS_BACK = 2
MAX_PER_RUN = 100
MAX_PER_USER = 5
DELAY_SECONDS = 2
REPOST_LOG_FILE = "reposted_bp.txt"   # uniek per account houden

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    print(f"{ts} {msg}")

def parse_created_dt(record, post):
    # probeer meerdere velden veilig
    for attr in ("createdAt", "indexedAt", "created_at", "timestamp"):
        val = getattr(record, attr, None) or getattr(post, attr, None)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                continue
    return None

def main():
    username = os.environ.get("BSKY_USERNAME_BP")
    password = os.environ.get("BSKY_PASSWORD_BP")
    if not username or not password:
        log("❌ Geen BSKY_USERNAME_BP / BSKY_PASSWORD_BP in env.")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    # repost-log laden
    done = set()
    if os.path.exists(REPOST_LOG_FILE):
        with open(REPOST_LOG_FILE, "r", encoding="utf-8") as f:
            done = set(line.strip() for line in f if line.strip())

    # feed ophalen
    try:
        log("📥 Ophalen feed...")
        feed = client.app.bsky.feed.get_feed({"feed": FEED_AT_URI, "limit": 100}).feed
        log(f"📊 {len(feed)} items in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)

    # filter geschikte posts
    posts = []
    for item in feed:
        post = item.post
        record = post.record
        uri = post.uri
        cid = post.cid

        # sla reposts/replies over
        if getattr(item, "reason", None):
            continue
        if getattr(record, "reply", None):
            continue

        # al eens gedaan?
        if uri in done:
            continue

        created = parse_created_dt(record, post)
        if not created or created < cutoff:
            continue

        posts.append({
            "uri": uri,
            "cid": cid,
            "author": getattr(post.author, "did", None),  # gebruik DID i.p.v. handle
            "created": created,
        })

    # Oudste eerst
    posts.sort(key=lambda p: p["created"])

    # per-user limiet voorselectie
    per_user = {}
    filtered = []
    for p in posts:
        if len(filtered) >= MAX_PER_RUN:
            break
        did = p["author"] or "unknown"
        if per_user.get(did, 0) >= MAX_PER_USER:
            continue
        per_user[did] = per_user.get(did, 0) + 1
        filtered.append(p)

    total = len(filtered)
    log(f"🧩 Geschikt voor verwerking: {total} (max {MAX_PER_RUN}, max {MAX_PER_USER}/user).")

    reposted = 0
    liked = 0
    for idx, p in enumerate(filtered, start=1):
        try:
            # repost
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "$type": "app.bsky.feed.repost",
                    "subject": {"uri": p["uri"], "cid": p["cid"]},
                    "createdAt": now_utc_iso(),
                },
            )
            reposted += 1
            done.add(p["uri"])

            # like
            try:
                client.app.bsky.feed.like.create(
                    repo=client.me.did,
                    record={
                        "$type": "app.bsky.feed.like",
                        "subject": {"uri": p["uri"], "cid": p["cid"]},
                        "createdAt": now_utc_iso(),
                    },
                )
                liked += 1
            except Exception:
                # like is nice-to-have, sla fout stil over
                pass

            # vertraging
            if idx < total:
                time.sleep(DELAY_SECONDS)

        except Exception:
            # mislukt: niet toevoegen aan done, gewoon verder
            continue

    # repost-log wegschrijven
    if done:
        with open(REPOST_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(done)))

    # eindteller
    log(f"✅ Klaar — {reposted} reposts uitgevoerd ({liked} geliked).")

if __name__ == "__main__":
    main()