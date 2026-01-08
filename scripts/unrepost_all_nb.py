from atproto import Client
import os
import time

# === SAFETY CONFIG ===
DEFAULT_LIMIT = 100          # items per page
DEFAULT_MAX_ACTIONS = 500    # max unreposts per run (safety cap)
DEFAULT_SLEEP_SECONDS = 0.15 # throttle


def is_repost_item(feed_item: dict) -> bool:
    """
    Author feed items that are reposts have a 'reason' with $type ending in 'reasonRepost'.
    """
    reason = feed_item.get("reason")
    if not reason:
        return False
    rtype = reason.get("$type", "")
    return rtype.endswith("reasonRepost")


def parse_at_uri(uri: str):
    # at://did:plc:xxxx/app.bsky.feed.repost/3lxyz...
    if not uri.startswith("at://"):
        raise ValueError(f"Not an at:// uri: {uri}")
    rest = uri[len("at://"):]
    parts = rest.split("/")
    if len(parts) < 3:
        raise ValueError(f"Unexpected at:// uri format: {uri}")
    repo = parts[0]
    collection = parts[1]
    rkey = parts[2]
    return repo, collection, rkey


def main():
    username = os.getenv("BSKY_USERNAME_NB")
    password = os.getenv("BSKY_PASSWORD_NB")

    if not username or not password:
        print("❌ Geen inloggegevens gevonden in env (BSKY_USERNAME_NB / BSKY_PASSWORD_NB).")
        return

    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    max_actions = int(os.getenv("MAX_ACTIONS", str(DEFAULT_MAX_ACTIONS)))
    sleep_s = float(os.getenv("SLEEP_SECONDS", str(DEFAULT_SLEEP_SECONDS)))

    client = Client()
    client.login(username, password)

    # In atproto python client: client.me.did is your DID
    my_did = client.me.did

    print(f"✅ Ingelogd als {username}")
    print(f"ℹ️ DID: {my_did}")
    print(f"ℹ️ dry_run={dry_run} max_actions={max_actions} sleep={sleep_s}s")

    cursor = None
    scanned = 0
    unreposted = 0
    skipped_no_uri = 0

    while True:
        params = {"actor": my_did, "limit": DEFAULT_LIMIT}
        if cursor:
            params["cursor"] = cursor

        res = client.app.bsky.feed.get_author_feed(params)

        # atproto client may return model objects; make robust by converting to dict when needed
        feed = getattr(res, "feed", None) or res.get("feed", [])
        cursor = getattr(res, "cursor", None) or res.get("cursor")

        if not feed:
            break

        for item in feed:
            # item can be model or dict
            item_dict = item.model_dump() if hasattr(item, "model_dump") else item
            scanned += 1

            if not is_repost_item(item_dict):
                continue

            reason = item_dict.get("reason", {}) or {}
            repost_uri = reason.get("uri")

            # fallback: sometimes the repost record URI is in viewer.repost
            if not repost_uri:
                post = item_dict.get("post", {}) or {}
                viewer = post.get("viewer", {}) or {}
                repost_uri = viewer.get("repost")

            if not repost_uri:
                skipped_no_uri += 1
                continue

            try:
                repo, collection, rkey = parse_at_uri(repost_uri)
            except Exception as e:
                print(f"⚠️ Kan repost_uri niet parsen: {repost_uri} ({e})")
                continue

            # extra safety: only delete your own repost records
            if repo != my_did or collection != "app.bsky.feed.repost":
                print(f"⚠️ Skip (niet jouw repost-record): {repost_uri}")
                continue

            print(f"UNREPOST: {repost_uri}")
            if not dry_run:
                client.com.atproto.repo.delete_record(
                    {"repo": repo, "collection": collection, "rkey": rkey}
                )

            unreposted += 1
            if unreposted >= max_actions:
                print(f"🛑 MAX_ACTIONS bereikt ({max_actions}). Stop run.")
                print(f"📊 scanned={scanned} unreposted={unreposted} skipped_no_uri={skipped_no_uri}")
                return

            time.sleep(sleep_s)

        if not cursor:
            break

    print("✅ Klaar.")
    print(f"📊 scanned={scanned} unreposted={unreposted} skipped_no_uri={skipped_no_uri}")
    if dry_run:
        print("ℹ️ Dit was een DRY RUN (er is niets verwijderd).")


if __name__ == "__main__":
    main()