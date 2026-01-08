from atproto import Client
import os
import time

# === SAFETY CONFIG ===
DEFAULT_LIMIT = 100
DEFAULT_MAX_ACTIONS = 500
DEFAULT_SLEEP_SECONDS = 0.15


def to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def is_repost_item(item: dict) -> bool:
    reason = item.get("reason")
    if not reason:
        return False
    return reason.get("$type", "").endswith("reasonRepost")


def parse_at_uri(uri: str):
    if not uri.startswith("at://"):
        raise ValueError("Invalid AT URI")
    parts = uri.replace("at://", "").split("/")
    return parts[0], parts[1], parts[2]


def main():
    username = os.getenv("BSKY_USERNAME_NB")
    password = os.getenv("BSKY_PASSWORD_NB")

    if not username or not password:
        print("❌ Missing BSKY_USERNAME_NB / BSKY_PASSWORD_NB")
        return

    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    max_actions = int(os.getenv("MAX_ACTIONS", DEFAULT_MAX_ACTIONS))
    sleep_s = float(os.getenv("SLEEP_SECONDS", DEFAULT_SLEEP_SECONDS))

    client = Client()
    client.login(username, password)

    my_did = client.me.did

    print(f"✅ Logged in as {username}")
    print(f"ℹ️ DID: {my_did}")
    print(f"ℹ️ dry_run={dry_run}")

    cursor = None
    unreposted = 0
    scanned = 0

    while True:
        params = {"actor": my_did, "limit": DEFAULT_LIMIT}
        if cursor:
            params["cursor"] = cursor

        res = client.app.bsky.feed.get_author_feed(params)
        feed = res.feed
        cursor = res.cursor

        if not feed:
            break

        for item in feed:
            item = to_dict(item)
            scanned += 1

            if not is_repost_item(item):
                continue

            reason = to_dict(item.get("reason", {}))
            repost_uri = reason.get("uri")

            if not repost_uri:
                post = to_dict(item.get("post", {}))
                viewer = to_dict(post.get("viewer", {}))
                repost_uri = viewer.get("repost")

            if not repost_uri:
                continue

            repo, collection, rkey = parse_at_uri(repost_uri)

            if repo != my_did or collection != "app.bsky.feed.repost":
                continue

            print(f"UNREPOST: {repost_uri}")

            if not dry_run:
                client.com.atproto.repo.delete_record(
                    repo=repo,
                    collection=collection,
                    rkey=rkey,
                )

            unreposted += 1
            if unreposted >= max_actions:
                print("🛑 MAX_ACTIONS reached")
                return

            time.sleep(sleep_s)

        if not cursor:
            break

    print(f"✅ Done — scanned={scanned}, unreposted={unreposted}")
    if dry_run:
        print("ℹ️ DRY RUN — nothing was deleted")


if __name__ == "__main__":
    main()