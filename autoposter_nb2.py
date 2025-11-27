from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

# === CONFIG ===
FEED_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaagavuywvbsu"
MAX_PER_RUN = 50
MAX_PER_USER = 3
HOURS_BACK = 4
DELAY_SECONDS = 2  # vertraging tussen reposts

REPOST_LOG = "reposted_nb.txt"

def log(msg: str):
    """Minimal logging zonder accountnamen."""
    now = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    print(f"{now} {msg}")

def main():
    username = os.getenv("BSKY_USERNAME_NB")
    password = os.getenv("BSKY_PASSWORD_NB")

    if not username or not password:
        print("❌ Geen login info gevonden via secrets!")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    # Feed ophalen
    try:
        log("📥 Feed ophalen...")
        feed = client.app.bsky.feed.get_feed({"feed": FEED_URI, "limit": 100}).feed
        log(f"📊 {len(feed)} posts gevonden in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    # Repost-log laden
    done = set()
    if os.path.exists(REPOST_LOG):
        with open(REPOST_LOG, "r") as f:
            done = set(f.read().splitlines())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    eligible_posts = []

    for item in feed:
        post = item.post
        record = post.record
        uri = post.uri
        cid = post.cid

        # Skip replies of al eerder gerepost
        if hasattr(item, "reason") and item.reason is not None:
            continue
        if getattr(record, "reply", None):
            continue
        if uri in done:
            continue

        created = getattr(record, "createdAt", None)
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except:
                continue
        else:
            continue

        if created_dt >= cutoff:
            eligible_posts.append({"uri": uri, "cid": cid, "created": created_dt})

    # Sorteer op oudste eerst
    eligible_posts.sort(key=lambda x: x["created"])
    eligible_posts = eligible_posts[:MAX_PER_RUN]

    log(f"🧩 {len(eligible_posts)} geschikte posts gevonden.")

    reposted = 0
    liked = 0
    user_count = {}

    for post in eligible_posts:
        if reposted >= MAX_PER_RUN:
            break

        uri = post["uri"]
        cid = post["cid"]

        try:
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": client.get_current_time_iso(),
                },
            )
            reposted += 1
            done.add(uri)
            time.sleep(DELAY_SECONDS)

            client.app.bsky.feed.like.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": client.get_current_time_iso(),
                },
            )
            liked += 1
            time.sleep(1)

        except Exception:
            continue

    # Opslaan repost-log
    with open(REPOST_LOG, "w") as f:
        f.write("\n".join(done))

    log(f"🔥 Klaar — {reposted} reposts uitgevoerd ({liked} geliked).")
    log(f"⏰ Run afgerond op {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == "__main__":
    main()