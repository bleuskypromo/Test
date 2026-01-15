import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Set, List, Dict, Optional
from atproto import Client, models

# === CONFIGURATION & CONSTANTS (from your environment) ===
ENV_USERNAME = os.getenv("BSKY_USERNAME_BP")
ENV_PASSWORD = os.getenv("BSKY_PASSWORD_BP")
STATE_FILE = "bot_state.json"

HOURS_BACK = int(os.getenv("HOURS_BACK", 3))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", 100))
MAX_PER_USER = int(os.getenv("MAX_PER_USER", 3))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", 2))
LIST_MEMBER_LIMIT = int(os.getenv("LIST_MEMBER_LIMIT", 1500))
AUTHOR_POSTS_PER_MEMBER = int(os.getenv("AUTHOR_POSTS_PER_MEMBER", 10))

# === UTILITIES ===

def log(message: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}", flush=True)

def load_state(filepath: str) -> dict:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"repost_records": {}, "like_records": {}, "user_interactions": {}}

def save_state(filepath: str, state: dict):
    try:
        # Prune old state records to keep file small (keep last 1000)
        state["like_records"] = dict(list(state["like_records"].items())[-1000:])
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"❌ Error saving state: {e}")

# === BOT CLASS ===

class BlueskyBot:
    def __init__(self):
        self.client = Client()
        self.state = load_state(STATE_FILE)
        self.count_this_run = 0

    def login(self):
        log(f"🔑 Logging in as {ENV_USERNAME}...")
        self.client.login(ENV_USERNAME, ENV_PASSWORD)

    def is_recent(self, created_at_str: str) -> bool:
        """Checks if the post is within the HOURS_BACK window."""
        try:
            # Normalize Z format
            dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt) < timedelta(hours=HOURS_BACK)
        except Exception:
            return False

    def can_interact(self, post_view) -> bool:
        """Applies filters: logic, recency, and per-user limits."""
        author_did = post_view.author.did
        uri = post_view.uri
        
        # 1. Skip if already liked
        if uri in self.state["like_records"]:
            return False
            
        # 2. Skip if it's our own post
        if author_did == self.client.me.did:
            return False

        # 3. Check per-user limit for this run
        user_total = self.state["user_interactions"].get(author_did, 0)
        if user_total >= MAX_PER_USER:
            return False

        # 4. Check recency
        if not self.is_recent(post_view.record.created_at):
            return False

        return True

    def interact(self, post_view):
        """Performs Like/Repost and updates state."""
        if self.count_this_run >= MAX_PER_RUN:
            return False

        try:
            log(f"⭐ Liking post by @{post_view.author.handle}")
            self.client.like(post_view.uri, post_view.cid)
            
            # Update state
            self.state["like_records"][post_view.uri] = datetime.now(timezone.utc).isoformat()
            self.state["user_interactions"][post_view.author.did] = self.state["user_interactions"].get(post_view.author.did, 0) + 1
            
            self.count_this_run += 1
            time.sleep(SLEEP_SECONDS)
            return True
        except Exception as e:
            log(f"⚠️ Interaction failed: {e}")
            return False

    def process_hashtag(self, tag: str):
        """Discovers content by searching a hashtag."""
        log(f"🔍 Searching for #{tag}...")
        try:
            results = self.client.app.bsky.feed.search_posts(params={"q": f"#{tag}", "limit": 50})
            for post in results.posts:
                if self.can_interact(post):
                    self.interact(post)
                if self.count_this_run >= MAX_PER_RUN:
                    break
        except Exception as e:
            log(f"⚠️ Search error for #{tag}: {e}")

    def process_list(self, list_uri: str):
        """Fetches members of a list and scans their recent feeds."""
        log(f"📋 Scanning list members: {list_uri}")
        try:
            # 1. Get List Members
            list_data = self.client.app.bsky.graph.get_list(params={"list": list_uri, "limit": 50})
            members = [item.subject.did for item in list_data.items]
            
            # 2. Iterate members and check their feeds
            for member_did in members[:LIST_MEMBER_LIMIT]:
                if self.count_this_run >= MAX_PER_RUN:
                    break
                
                log(f"👤 Checking member feed: {member_did}")
                feed = self.client.get_author_feed(actor=member_did, limit=AUTHOR_POSTS_PER_MEMBER)
                
                for item in feed.feed:
                    # Skip reposts in the feed; only interact with original content
                    if not hasattr(item, 'reason') or item.reason is None:
                        if self.can_interact(item.post):
                            self.interact(item.post)
        except Exception as e:
            log(f"⚠️ List processing error: {e}")

# === EXECUTION ===

if __name__ == "__main__":
    bot = BlueskyBot()
    try:
        bot.login()
        
        # Reset per-run user counter
        bot.state["user_interactions"] = {}

        # EXAMPLE: Scan a Hashtag
        bot.process_hashtag("python")

        # EXAMPLE: Scan a List (Uncomment and replace with your list URI)
        # my_list_uri = "at://did:plc:xxx/app.bsky.graph.list/3k..."
        # bot.process_list(my_list_uri)

        log(f"✅ Finished run. Total interactions: {bot.count_this_run}")
    except Exception as e:
        log(f"💥 Critical Error: {e}")
    finally:
        save_state(STATE_FILE, bot.state)