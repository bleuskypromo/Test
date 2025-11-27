from atproto import Client
import os
from datetime import datetime, timedelta, timezone

# === CONFIG ===
FEED_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaagavuywvbsu"
MAX_PER_RUN = 100          # max aantal reposts per run
MAX_PER_USER = 3          # max per user per run
HOURS_BACK = 3            # kijk laatste 3 uur terug
REPOST_LOG_FILE = "reposted_nb2.txt"  # eigen log voor nsfwbleusky

def log(msg: str):
    """Eenvoudige logregel zonder accountnamen."""
    now = datetime.now(timezone.utc).strftime("[%H:%M:%S]")
    print(f"{now} {msg}")

def parse_time(record, post):
    """Zoekt een bruikbare timestamp op verschillende plekken/velden."""
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
        log("❌ Geen BSKY_USERNAME_NB/BSKY_PASSWORD_NB in env gevonden.")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    # Feed ophalen
    try:
        log("📥 Feed ophalen...")
        feed = client.app.bsky.feed.get_feed({"feed": FEED_URI, "limit": 100})
        items = feed.feed
        log(f"📊 {len(items)} posts gevonden in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    # Repost-log laden (alleen URIs, geen namen)
    done = set()
    if os.path.exists(REPOST_LOG_FILE):
        with open(REPOST_LOG_FILE, "r", encoding="utf-8") as f:
            done = set(f.read().splitlines())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)

    eligible_posts = []
    # tellers om te zien WAAROM posts afvallen
    cnt_reposts = 0
    cnt_replies = 0
    cnt_already_done = 0
    cnt_no_time = 0
    cnt_too_old = 0

    for item in items:
        post = item.post
        record = post.record
        uri = post.uri
        cid = post.cid
        author_id = getattr(post.author, "did", None)

        # skip reposts
        if getattr(item, "reason", None) is not None:
            cnt_reposts += 1
            continue

        # skip replies
        if getattr(record, "reply", None):
            cnt_replies += 1
            continue

        # al eens gedaan door deze bot
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

        eligible_posts.append(
            {
                "uri": uri,
                "cid": cid,
                "author_id": author_id,
                "created": created_dt,
            }
        )

    log(
        f"🧩 {len(eligible_posts)} geschikte posts gevonden "
        f"(reposts: {cnt_reposts}, replies: {cnt_replies}, "
        f"al gedaan: {cnt_already_done}, geen tijd: {cnt_no_time}, te oud: {cnt_too_old})"
    )

    if not eligible_posts:
        log("🔥 Klaar — 0 reposts uitgevoerd (0 geliked).")
        log(
            f"ℹ️ Tip: als dit vaker gebeurt, vergroot tijdelijk HOURS_BACK "
            f"of controleer of de feed de laatste uren wel nieuwe posts heeft."
        )
        return

    # oudste eerst
    eligible_posts.sort(key=lambda x: x["created"])

    reposted = 0
    liked = 0
    per_user_count = {}

    for post in eligible_posts:
        if reposted >= MAX_PER_RUN:
            break

        author_id = post["author_id"] or "unknown"
        uri = post["uri"]
        cid = post["cid"]

        per_user_count[author_id] = per_user_count.get(author_id, 0)
        if per_user_count[author_id] >= MAX_PER_USER:
            continue

        # Repost
        try:
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                },
            )
            reposted += 1
            per_user_count[author_id] += 1
            done.add(uri)
        except Exception as e:
            log(f"⚠️ Fout bij repost (samengevat): {e}")
            continue

        # Like
        try:
            client.app.bsky.feed.like.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                },
            )
            liked += 1
        except Exception as e:
            log(f"⚠️ Fout bij like (samengevat): {e}")

    # logbestand bijwerken
    with open(REPOST_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(done))

    log(f"🔥 Klaar — {reposted} reposts uitgevoerd ({liked} geliked).")
    log(f"⏰ Run afgerond op {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == "__main__":
    main()