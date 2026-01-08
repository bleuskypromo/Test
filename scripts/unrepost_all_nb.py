from atproto import Client
import os
import time

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

    print("✅ Logged in.")
    print(f"ℹ️ dry_run={dry_run} max_actions={max_actions}")

    # Pass 1: count ALL repost records
    cursor = None
    total = 0
    while True:
        params = {"repo": my_did, "collection": COLLECTION, "limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor

        res = client.com.atproto.repo.list_records(params)
        records = getattr(res, "records", []) or []
        cursor = getattr(res, "cursor", None)

        if not records:
            break

        total += len(records)

        if not cursor:
            break

    print(f"📊 Total repost-records found: {total}")

    # If you want ONLY the count, stop here:
    if os.getenv("COUNT_ONLY", "true").lower() == "true":
        return

    # Pass 2 (optional): delete up to MAX_ACTIONS (minimal logging)
    cursor = None
    deleted = 0
    while True:
        params = {"repo": my_did, "collection": COLLECTION, "limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor

        res = client.com.atproto.repo.list_records(params)
        records = getattr(res, "records", []) or []
        cursor = getattr(res, "cursor", None)

        if not records:
            break

        for rec in records:
            uri = getattr(rec, "uri", None)
            if not uri:
                continue

            parts = uri.replace("at://", "").split("/")
            if len(parts) < 3:
                continue

            repo, collection, rkey = parts[0], parts[1], parts[2]
            if repo != my_did or collection != COLLECTION:
                continue

            if not dry_run:
                client.com.atproto.repo.delete_record(
                    repo=repo,
                    collection=collection,
                    rkey=rkey,
                )

            deleted += 1
            if deleted >= max_actions:
                print(f"🛑 Deleted this run: {deleted}")
                return

            time.sleep(sleep_s)

        if not cursor:
            break

    print(f"✅ Deleted this run: {deleted}")


if __name__ == "__main__":
    main()