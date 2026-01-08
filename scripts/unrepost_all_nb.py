from atproto import Client
import os
import time

# --- CONFIG ---
COLLECTION = "app.bsky.feed.repost"
PAGE_LIMIT = 100

DEFAULT_MAX_ACTIONS = 500
DEFAULT_SLEEP_SECONDS = 0.15


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
    print(f"ℹ️ dry_run={dry_run} max_actions={max_actions} sleep={sleep_s}s")

    cursor = None
    scanned = 0
    deleted = 0

    while True:
        params = {
            "repo": my_did,
            "collection": COLLECTION,
            "limit": PAGE_LIMIT,
        }
        if cursor:
            params["cursor"] = cursor

        res = client.com.atproto.repo.list_records(params)

        # res is a Response model
        records = getattr(res, "records", []) or []
        cursor = getattr(res, "cursor", None)

        if not records:
            break

        for rec in records:
            # rec has: uri, cid, value
            # Example uri: at://did:plc:.../app.bsky.feed.repost/<rkey>
            uri = getattr(rec, "uri", None)
            scanned += 1

            if not uri or not uri.startswith("at://"):
                continue

            # parse rkey from uri
            # at://<did>/<collection>/<rkey>
            parts = uri.replace("at://", "").split("/")
            if len(parts) < 3:
                continue

            repo = parts[0]
            collection = parts[1]
            rkey = parts[2]

            if repo != my_did or collection != COLLECTION:
                continue

            print(f"UNREPOST-RECORD: {uri}")

            if not dry_run:
                client.com.atproto.repo.delete_record(
                    repo=repo,
                    collection=collection,
                    rkey=rkey,
                )

            deleted += 1
            if deleted >= max_actions:
                print(f"🛑 MAX_ACTIONS reached ({max_actions}). Stop run.")
                print(f"📊 scanned={scanned} deleted={deleted}")
                return

            time.sleep(sleep_s)

        if not cursor:
            break

    print(f"✅ Done — scanned={scanned}, unreposted(deleted)={deleted}")
    if dry_run:
        print("ℹ️ DRY RUN — nothing was deleted")


if __name__ == "__main__":
    main()