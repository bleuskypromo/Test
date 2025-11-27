from atproto import Client
import os
import time
from datetime import datetime, timedelta, timezone

# === CONFIG ===
FEED_URI = "at://did:plc:jaka644beit3x4vmmg6yysw7/app.bsky.feed.generator/aaagavuywvbsu"
MAX_PER_RUN = 100         # max aantal reposts per run
MAX_PER_USER = 3          # max per gebruiker per run
HOURS_BACK = 5            # kijk 5 uur terug (test); later kun je dit naar 1.5 zetten
REPOST_LOG_FILE = "reposted_nb2.txt"  # eigen log voor nsfw-acc

def log(msg: str):
    """Eenvoudige console-log met tijd, zonder accountnamen/URI's."""
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

def parse_time(record, post):
    """Zoek bruikbare timestamp in record of post."""
    for attr in ["createdAt", "indexedAt", "created_at", "timestamp"]:
        val = getattr(record, attr, None) or getattr(post, attr, None)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                continue
    return None

def load_repost_log(path: str):
    """Lees eerder gereposte URI's in uit txt-bestand."""
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return set(lines)

def save_repost_log(path: str, uris: set):
    """Schrijf bijgewerkte lijst van gereposte URI's naar txt-bestand."""
    with open(path, "w", encoding="utf-8") as f:
        for uri in uris:
            f.write(uri + "\n")

def main():
    username = os.getenv("BSKY_USERNAME_NB")
    password = os.getenv("BSKY_PASSWORD_NB")

    if not username or not password:
        log("❌ Geen inloggegevens gevonden in env (BSKY_USERNAME_NB / BSKY_PASSWORD_NB).")
        return

    client = Client()
    client.login(username, password)
    log("✅ Ingelogd.")

    # Feed ophalen
    log("📥 Feed ophalen...")
    try:
        feed = client.app.bsky.feed.get_feed({"feed": FEED_URI, "limit": 100})
        items = feed.feed
        log(f"📊 {len(items)} posts gevonden in feed.")
    except Exception as e:
        log(f"⚠️ Fout bij ophalen feed: {e}")
        return

    # Repost-log laden
    done = load_repost_log(REPOST_LOG_FILE)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)

    candidates = []

    # Alle items uit de feed inspecteren
    for item in items:
        post = item.post
        record = post.record
        uri = post.uri
        cid = post.cid

        # Reposts en replies overslaan
        if hasattr(item, "reason") and item.reason is not None:
            continue
        if getattr(record, "reply", None):
            continue

        # Al eens gedaan?
        if uri in done:
            continue

        created_dt = parse_time(record, post)
        if not created_dt:
            continue
        if created_dt < cutoff:
            continue

        candidates.append({
            "uri": uri,
            "cid": cid,
            "created": created_dt,
            # we slaan de handle niet op in log, alleen intern als key
            "author_did": getattr(post.author, "did", None),
        })

    # Oudste eerst
    candidates.sort(key=lambda x: x["created"])

    log(f"🧩 {len(candidates)} geschikte posts gevonden.")

    reposted = 0
    liked = 0
    per_user_count = {}

    for post in candidates:
        if reposted >= MAX_PER_RUN:
            break

        author_key = post["author_did"] or "unknown"
        per_user_count[author_key] = per_user_count.get(author_key, 0)
        if per_user_count[author_key] >= MAX_PER_USER:
            continue

        uri = post["uri"]
        cid = post["cid"]

        try:
            # Repost
            client.app.bsky.feed.repost.create(
                repo=client.me.did,
                record={
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            reposted += 1
            per_user_count[author_key] += 1
            done.add(uri)

            # Like
            try:
                client.app.bsky.feed.like.create(
                    repo=client.me.did,
                    record={
                        "subject": {"uri": uri, "cid": cid},
                        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                )
                liked += 1
            except Exception as e_like:
                log(f"⚠️ Fout bij liken (intern gelogd): {e_like}")

            # Korte vertraging tussen posts
            time.sleep(2)

        except Exception as e:
            log(f"⚠️ Fout bij repost (intern gelogd): {e}")

    # Repost-log opslaan
    save_repost_log(REPOST_LOG_FILE, done)

    log(f"🔥 Klaar — {reposted} reposts uitgevoerd ({liked} geliked).")
    log(f"⏰ Run afgerond op {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == "__main__":
    main()