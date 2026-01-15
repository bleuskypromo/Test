import os
import time
import random
from typing import Set, List, Dict, Optional, Tuple

# Assuming these are imported from your framework/library

# imports
from atproto import Client
import os
...

print("=== STARTING BOT ===", flush=True)

# -------------------------
# helpers (ALTIJD EERST)
# -------------------------
def log(msg: str):
    ...

def utcnow():
    ...

def parse_time(...):
    ...

def is_quote_post(...):
    ...

def has_media(...):
    ...

# alle andere helper functies
# normalize_*, fetch_*, repost_and_like, etc.

# -------------------------
# MAIN PAS HIERNA
# -------------------------
def main():
    log("🚀 main() entered")
    ...
# from your_utils import (log, utcnow, load_state, save_state, normalize_feed_uri, 
#                        normalize_list_uri, normalize_post_uri, fetch_author_feed, 
#                        fetch_feed_items, fetch_list_members, fetch_hashtag_posts, 
#                        build_candidates_from_feed_items, build_candidates_from_postviews,
#                        get_postview_by_uri, is_quote_post, has_media, repost_and_like)

def pick_random_post_from_actor_unlimited(
    client: "Client",
    actor: str,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
) -> Optional[Tuple[str, str]]:
    """Fetches a feed from a specific actor and picks a random post matching criteria."""
    items = fetch_author_feed(client, actor, SLOT_AUTHOR_FEED_LIMIT)
    eligible: List[Tuple[str, str]] = []

    for item in items:
        post = getattr(item, "post", None)
        if not post or (hasattr(item, "reason") and item.reason is not None):
            continue

        record = getattr(post, "record", None)
        if not record or getattr(record, "reply", None) or is_quote_post(record) or not has_media(record):
            continue

        author = getattr(post, "author", None)
        ah = (getattr(author, "handle", "") or "").lower()
        ad = (getattr(author, "did", "") or "").lower()
        if ah in exclude_handles or ad in exclude_dids:
            continue

        uri = getattr(post, "uri", None)
        cid = getattr(post, "cid", None)
        if uri and cid:
            eligible.append((uri, cid))

    return random.choice(eligible) if eligible else None


def main():
    log("🚀 main() entered")

    # 1. Setup and Auth
    username = os.getenv(ENV_USERNAME, "").strip()
    password = os.getenv(ENV_PASSWORD, "").strip()
    if not username or not password:
        log(f"❌ Missing env {ENV_USERNAME} / {ENV_PASSWORD}")
        return

    cutoff = utcnow() - timedelta(hours=HOURS_BACK)
    log(f"Cutoff = {cutoff.isoformat()} (HOURS_BACK={HOURS_BACK})")

    state = load_state(STATE_FILE)
    repost_records = state.get("repost_records", {})
    like_records = state.get("like_records", {})

    log("Logging in...")
    client = Client()
    client.login(username, password)
    me = client.me.did
    log(f"✅ Logged in as {me}")

    # 2. Normalize Feeds and Lists
    feed_uris = [(k, v.get("note", ""), normalize_feed_uri(client, v.get("link", ""))) 
                 for k, v in FEEDS.items() if v.get("link")]
    list_uris = [(k, v.get("note", ""), normalize_list_uri(client, v.get("link", ""))) 
                 for k, v in LIJSTEN.items() if v.get("link")]
    excl_uris = [(k, v.get("note", ""), normalize_list_uri(client, v.get("link", ""))) 
                 for k, v in EXCLUDE_LISTS.items() if v.get("link")]

    # 3. Build Exclude Sets
    exclude_handles, exclude_dids = set(), set()
    for key, note, luri in [u for u in excl_uris if u[2]]:
        log(f"🚫 Loading exclude list: {key}")
        members = fetch_list_members(client, luri, limit=max(1000, LIST_MEMBER_LIMIT))
        for h, d in members:
            if h: exclude_handles.add(h.lower())
            if d: exclude_dids.add(d.lower())

    # 4. Collect Candidates
    all_candidates = []

    # From Feeds
    for key, note, furi in [u for u in feed_uris if u[2]]:
        items = fetch_feed_items(client, furi, max_items=FEED_MAX_ITEMS)
        all_candidates.extend(build_candidates_from_feed_items(items, cutoff, exclude_handles, exclude_dids))

    # From Lists
    for key, note, luri in [u for u in list_uris if u[2]]:
        members = fetch_list_members(client, luri, limit=max(1000, LIST_MEMBER_LIMIT))
        for (h, d) in members:
            actor = d or h
            if actor:
                author_items = fetch_author_feed(client, actor, AUTHOR_POSTS_PER_MEMBER)
                all_candidates.extend(build_candidates_from_feed_items(author_items, cutoff, exclude_handles, exclude_dids))

    # From Hashtags
    hashtag_posts = fetch_hashtag_posts(client, HASHTAG_MAX_ITEMS)
    all_candidates.extend(build_candidates_from_postviews(hashtag_posts, cutoff, exclude_handles, exclude_dids))

    # Deduplicate and Sort
    seen = set()
    candidates = []
    for c in sorted(all_candidates, key=lambda x: x["created"]):
        if c["uri"] not in seen:
            seen.add(c["uri"])
            candidates.append(c)

    log(f"🧩 Candidates total: {len(candidates)}")

    # 5. Execution Logic
    total_done = 0
    per_user_count = {}

    def run_slot(pos: int):
        nonlocal total_done
        if total_done >= MAX_PER_RUN: return

        # Slot 3: Specific Promotion Post
        if pos == 3:
            promo_uri = normalize_post_uri(client, SINGLE_PROMO_POST)
            pv = get_postview_by_uri(client, promo_uri) if promo_uri else None
            if not pv: return
            
            record = getattr(pv, "record", None)
            author = getattr(pv, "author", None)
            ah = (getattr(author, "handle", "") or "").lower()
            ad = (getattr(author, "did", "") or "").lower()

            if (not record or getattr(record, "reply", None) or is_quote_post(record) or 
                not has_media(record) or ah in exclude_handles or ad in exclude_dids):
                return

            if repost_and_like(client, me, pv.uri, pv.cid, repost_records, like_records, True):
                total_done += 1
            return

        # Slots 4, 5, 6: Random Pick from Specific Actors
        actor_map = {4: SLOT4_ACTOR, 5: SLOT5_ACTOR, 6: SLOT6_ACTOR}
        actor = actor_map.get(pos)
        if actor:
            log(f"🎲 Slot{pos}: actor={actor}")
            pick = pick_random_post_from_actor_unlimited(client, actor, exclude_handles, exclude_dids)
            if pick and repost_and_like(client, me, pick[0], pick[1], repost_records, like_records, True):
                total_done += 1

    # Execute Priority Slots
    log("🚀 Running slots 3-6 first...")
    for pos in (3, 4, 5, 6):
        run_slot(pos)
        time.sleep(SLEEP_SECONDS)

    # Execute Normal Candidates
    log("🚀 Running normal candidates...")
    for c in candidates:
        if total_done >= MAX_PER_RUN: break
        
        author_key = c["author_key"]
        per_user_count.setdefault(author_key, 0)
        
        if per_user_count[author_key] < MAX_PER_USER:
            if repost_and_like(client, me, c["uri"], c["cid"], repost_records, like_records, False):
                total_done += 1
                per_user_count[author_key] += 1
                log(f"✅ Repost: {c['uri']}")
                time.sleep(SLEEP_SECONDS)

    # 6. Finalize State
    state["repost_records"] = repost_records
    state["like_records"] = like_records
    save_state(STATE_FILE, state)
    log(f"🔥 Done — total reposts this run: {total_done}")


if __name__ == "__main__":
    print("=== STARTING BOT ===", flush=True)
    try:
        main()
    except Exception:
        import traceback
        print("=== FATAL ERROR ===", flush=True)
        traceback.print_exc()