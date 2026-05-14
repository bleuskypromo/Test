import os
import json
from atproto import Client

USERNAME = os.environ["BSKY_USERNAME_PORNFEED"]
PASSWORD = os.environ["BSKY_PASSWORD_PORNFEED"]

HASHTAGS = [
    "bskypromo",
    "nsfw",
    "milf",
    "tittytuesday"
]

STATE_FILE = "state_pornfeed.json"
MAX_PER_RUN = 20


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"reposted": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


client = Client()
client.login(USERNAME, PASSWORD)

state = load_state()
done = 0

for tag in HASHTAGS:
    print(f"Searching #{tag}")

    results = client.app.bsky.feed.search_posts({
        "q": f"#{tag}",
        "limit": 50,
    })

    for post in results.posts:
        uri = post.uri
        cid = post.cid

        if uri in state["reposted"]:
            continue

        try:
            client.repost(uri, cid)
            client.like(uri, cid)

            state["reposted"].append(uri)
            done += 1

            print(f"Reposted: {uri}")

            if done >= MAX_PER_RUN:
                break

        except Exception as e:
            print(f"Error: {e}")

    if done >= MAX_PER_RUN:
        break

save_state(state)

print(f"Done. Reposted {done} posts.")