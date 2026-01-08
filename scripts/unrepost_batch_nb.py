from atproto import Client
import os
import time

COLLECTION = "app.bsky.feed.repost"
PAGE_LIMIT = 100

def count_reposts(client, did):
    cursor = None
    total = 0
    while True:
        params = {"repo": did, "collection": COLLECTION, "limit": PAGE_LIMIT}
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

    return total

def delete_batch(client, did, max_actions, sleep_s):
    cursor = None
    deleted = 0

    while True:
        params = {"repo": did, "collection": COLLECTION, "limit": PAGE_LIMIT}
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
            if repo != did or collection != COLLECTION:
                continue

            # ✅ atproto in jouw GH runner wil een dict als 'data'
            client.com.atproto.repo.delete_record({
                "repo": repo,
                "collection": collection,
                "rkey": rkey,
            })

            deleted += 1
            if deleted >= max_actions:
                return deleted

            time.sleep(sleep_s)

        if not cursor:
            break

    return deleted

def main():
    username = os.getenv("BSKY_USERNAME_NB")
    password = os.getenv("BSKY_PASSWORD_NB")
    if not username or not password:
        print("❌ Missing BSKY_USERNAME_NB / BSKY_PASSWORD_NB")
        return

    max_actions = int(os.getenv("MAX_ACTIONS", "2000"))
    sleep_s = float(os.getenv("SLEEP_SECONDS", "0.3"))

    client = Client()
    client.login(username, password)
    did = client.me.did

    remaining = count_reposts(client, did)
    print(f"📊 Remaining repost-records: {remaining}")

    if remaining == 0:
        print("✅ Nothing to do.")
        return

    deleted = delete_batch(client, did, max_actions=max_actions, sleep_s=sleep_s)
    print(f"🧹 Deleted this run: {deleted}")

if __name__ == "__main__":
    main()