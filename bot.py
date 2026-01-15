import os
import json
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Set, List, Dict, Optional, Tuple
from atproto import Client # Ensure you have 'atproto' installed via pip

# === CONFIGURATION & CONSTANTS ===
ENV_USERNAME = "BSKY_USERNAME_BP"
ENV_PASSWORD = "BSKY_PASSWORD_BP"
STATE_FILE = "bot_state.json"
HOURS_BACK = int(os.getenv("HOURS_BACK", 3))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", 100))
MAX_PER_USER = int(os.getenv("MAX_PER_USER", 3))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", 2))
LIST_MEMBER_LIMIT = int(os.getenv("LIST_MEMBER_LIMIT", 1500))
AUTHOR_POSTS_PER_MEMBER = int(os.getenv("AUTHOR_POSTS_PER_MEMBER", 10))
FEED_MAX_ITEMS = int(os.getenv("FEED_MAX_ITEMS", 500))
HASHTAG_MAX_ITEMS = int(os.getenv("HASHTAG_MAX_ITEMS", 100))
SLOT_AUTHOR_FEED_LIMIT = 50

# === BASIC UTILITIES ===

def log(message: str):
    """Simple timestamped logger."""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}", flush=True)

def utcnow():
    """Returns current UTC time."""
    return datetime.now(timezone.utc)

def load_state(filepath: str) -> dict:
    """Loads the progress state from a JSON file."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️ Error loading state: {e}")
    return {"repost_records": {}, "like_records": {}}

def save_state(filepath: str, state: dict):
    """Saves the progress state to a JSON file."""
    try:
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"❌ Error saving state: {e}")

# === BLUESKY SPECIFIC HELPERS ===
# You need to ensure these are defined or imported based on your specific requirements
# (The functions below are placeholders for the ones called in your main script)

def is_quote_post(record) -> bool:
    return hasattr(record, 'embed') and record.embed is not None and "embed.record" in str(type(record.embed))

def has_media(record) -> bool:
    # Basic check for images or external media
    return hasattr(record, 'embed') and record.embed is not None

# ... include your other logic functions (fetch_author_feed, etc.) here ...