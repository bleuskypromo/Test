import asyncio
import os
from atproto import Client, client_utils

FEED_URL = "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/feed/aaae6jfc5w2oi"
MAX_TOTAL = 50
MAX_PER_USER = 3
DELAY_SECONDS = 2


async def main():
    client = Client()
    client.login(os.getenv("BSKY_USERNAME_BP"), os.getenv("BSKY_PASSWORD_BP"))

    print("Fetching feed...")
    feed = client_utils.get_feed(client, FEED_URL)

    # Verzamelen van posts die nog niet gerepost zijn
    posts = [
        i.post
        for i in feed.feed
        if not getattr(i, "viewer", None) or not getattr(i.viewer, "repost", None)
    ]

    # Oudste eerst
    posts = list(reversed(posts))

    repost_count = 0
    like_count = 0
    per_user_count = {}

    for post in posts:
        if repost_count >= MAX_TOTAL:
            break

        author = post.author.did

        # Per-user limit
        if per_user_count.get(author, 0) >= MAX_PER_USER:
            continue

        try:
            client.like(post.uri, post.cid)
            like_count += 1
            print("Liked 1 post")
            await asyncio.sleep(DELAY_SECONDS)

            client.repost(post.uri, post.cid)
            repost_count += 1
            per_user_count[author] = per_user_count.get(author, 0) + 1

            print("Reposted 1 post")
            await asyncio.sleep(DELAY_SECONDS)

        except Exception as e:
            print("Error while posting:", e)

    print(f"Done. {like_count} liked, {repost_count} reposted.")


if __name__ == "__main__":
    asyncio.run(main())
