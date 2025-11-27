from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

# === CONFIG ===
FEED_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaagavuywvbsu"
MAX_PER_RUN = 100          # max reposts per run
MAX_PER_USER = 3          # max per user per run
HOURS_BACK = 2            # kijk laatste 4 uur terug
REPOST_LOG_FILE = "reposted_nb2.txt"  # eigen logbestand voor nsfwbleusky
DELAY_SECONDS = 2         # <---- 2 seconden vertraging per actie

def log(msg: str):
    now = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    print(f"{now} {msg}")

def parse_time(record, post):
    """Zoekt een bruikbare timestamp."""
    for attr in ["createdAt", "indexedAt", "created_at", "timestamp"]:
        val = getattr(record, attr, None) or getattr(post, attr, None)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                continue
    return None

def main():
    username = os.environ.get("BSKY_USERNAME_NB")
    password = os.environ.get("BSKY_PASSWORD_NB")

    if not username or not password:
        log("❌ Geen BSKY_USERNAME_NB/BSKY_PASSWORD_NB gevonden in secrets.")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    # Feed ophalen
    try:
        log("📥 Feed ophalen...")
        feed = client.app.bsky.feed.get_feed({"feed": FEED_URI, "limit": 100})
        items = feed.feed
        log(f"📊 {len(items)} posts gevonden.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    # Repost-log laden
    done = set()
    if os.path.exists(REPOST_LOG_FILE):
        with open(REPOST_LOG_FILE, "r", encoding="utf-8") as f:
            done = set(f.read().splitlines())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    eligible_posts = []

    # Analyse counters
    cnt_reposts = cnt_replies = cnt_already_done = cnt_no_time = cnt_too_old = 0

    for item in items:
        post = item.post
        record = post.record
        uri = post.uri
        cid = post.cid
        author_id = getattr(post.author, "did", "unknown")

        # Skip reposts
        if getattr(item, "reason", None) is not None:
            cnt_reposts += 1
            continue

        # Skip replies
        if getattr(record, "reply", None):
            cnt_replies += 1
            continue

        # Skip al verwerkt
        if uri in done:
            cnt_already_done += 1
            continue

        created_dt = parse_time(record, post)
        if not created_dt:
            cnt_no_time += 1
            continue

        if created_dt < cutoff:
            cnt_too_old += 1
            continue

        eligible_posts.append({
            "uri": uri,
            "cid": cid,
            "author_id": author_id,
            "created": created_dt,
        })

    log(
        f"🧩 {len(eligible_posts)} geschikte posts "
        f"(reposts:{cnt_reposts}, replies:{cnt_replies}, al gedaan:{cnt_already_done}, "
        f"geen tijd:{cnt_no_time}, te oud:{cnt_too_old})"
    )

    if not eligible_posts:
        log("😴 Geen nieuwe posts binnen tijdsvenster.")
        return

    # Sorteer van oud → nieuw
    eligible_posts.sort(key=lambda x: x["created"])

    reposted = 0
    liked = 0
    per_user_count = {}

    for post in eligible_posts:
        if reposted >= MAX_PER_RUN:
            break

        author = post["author_id"]
        uri = post["uri"]
        cid = post["cid"]

        per_user_count[author] = per_user_count.get(author, 0)
        if per_user_count[author] >= MAX_PER_USER:
            continue

        try:
            # Repost
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            time.sleep(DELAY_SECONDS)  # === VERTRAGING 2s
            reposted += 1
            per_user_count[author] += 1
            done.add(uri)

            # Like
            client.app.bsky.feed.like.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            time.sleep(DELAY_SECONDS)  # === VERTRAGING 2s
            liked += 1

        except Exception as e:
            log(f"⚠️ Fout bij repost/like (samengevat): {e}")

    # Update log
    with open(REPOST_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(done))

    log(f"🔥 Klaar — {reposted} reposts uitgevoerd ({liked} geliked)")
    log(f"⏰ Run voltooid om {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")