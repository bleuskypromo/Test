from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

# === CONFIG ===
FEED_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaagavuywvbsu"  # Jouw juiste feed
MAX_PER_RUN = 100
MAX_PER_USER = 3
HOURS_BACK = 2  # posts uit de laatste 1.5 uur
WAIT_SECONDS = 2  # vertraging tussen reposts

LOG_FILE = "autoposter_log_nb2.txt"
REPOST_FILE = "reposted_nb2.txt"


def log(msg: str):
    now = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    entry = f"{now} {msg}"
    print(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def reset_repost_log():
    """Reset repost-log als er niets nieuw is (bij setup/test)"""
    if os.path.exists(REPOST_FILE):
        os.remove(REPOST_FILE)
        log("🧹 repost-log opnieuw aangemaakt (test/reset).")


def main():
    username = os.environ["BSKY_USERNAME_NB"]
    password = os.environ["BSKY_PASSWORD_NB"]

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    log("🔍 Debug: login compleet, start feed-fetch...")

    try:
        log("📥 Feed ophalen...")
        feed = client.app.bsky.feed.get_feed({"feed": FEED_URI, "limit": 100})
        items = feed.feed
        log(f"📊 {len(items)} posts gevonden in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij feed ophalen: {e}")
        return

    done = set()
    if os.path.exists(REPOST_FILE):
        with open(REPOST_FILE, "r") as f:
            done = set(f.read().splitlines())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    all_posts = []
    per_user = {}

    for item in items:
        post = item.post
        record = post.record

        uri = post.uri
        cid = post.cid
        handle = getattr(post.author, "handle", "unknown")

        created_at = getattr(record, "createdAt", None)
        if created_at:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            continue

        if created_dt < cutoff:
            continue
        if uri in done:
            continue

        if getattr(record, "reply", None):
            continue

        all_posts.append({
            "uri": uri,
            "cid": cid,
            "author": handle,
            "created": created_dt,
        })

    if not all_posts:
        log("🔎 Geen geschikte nieuwe posts gevonden.")
        reset_repost_log()  # eenmalig voor test
        return

    all_posts.sort(key=lambda x: x["created"])  # oudste eerst

    repost_count = 0
    like_count = 0

    for post in all_posts:
        if repost_count >= MAX_PER_RUN:
            break
        if per_user.get(post["author"], 0) >= MAX_PER_USER:
            continue

        try:
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": post["uri"], "cid": post["cid"]},
                    "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            repost_count += 1
            per_user[post["author"]] = per_user.get(post["author"], 0) + 1
            done.add(post["uri"])
            time.sleep(WAIT_SECONDS)

            client.app.bsky.feed.like.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": post["uri"], "cid": post["cid"]},
                    "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            like_count += 1
            time.sleep(1)

        except Exception as e:
            log(f"⚠️ repost/like fout: {e}")

    with open(REPOST_FILE, "w") as f:
        f.write("\n".join(done))

    log(f"🔥 Klaar — {repost_count} reposts uitgevoerd ({like_count} geliked).")
    log(f"🔚 Run afgerond op {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")


if __name__ == "__main__":
    main()