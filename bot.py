from atproto import Client
import os
import re
import time
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Set, Tuple

# ===== HARD OUTPUT FIX (GitHub Actions) =====
try:
    sys.stdout.reconfigure(line_buffering=True)  # py3.7+
except Exception:
    pass

print("=== BOT STARTED (top-level) ===", flush=True)

# ============================================================
# CONFIG — leeg = skip
# ============================================================

FEEDS = {
    "feed 1": {"link": "", "note": "PROMO (bovenaan)"},
    "feed 2": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/feed/aaabjeu5724em",
        "note": "mentions",
    },
    "feed 3": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/feed/aaae6jfc5w2oi",
        "note": "bleuskypromo feed",
    },
    "feed 4": {"link": "", "note": ""},
    "feed 5": {"link": "", "note": ""},
    "feed 6": {"link": "", "note": ""},
    "feed 7": {"link": "", "note": ""},
    "feed 8": {"link": "", "note": ""},
    "feed 9": {"link": "", "note": ""},
    "feed 10": {"link": "", "note": ""},
}

LIJSTEN = {
    "lijst 1": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/lists/3m4so4mob5p2i",
        "note": "PROMO (bovenaan)",
    },
    "lijst 2": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/lists/3m3iga6wnmz2p",
        "note": "Beautygroup list",
    },
    "lijst 3": {"link": "", "note": ""},
    "lijst 4": {"link": "", "note": ""},
    "lijst 5": {"link": "", "note": ""},
    "lijst 6": {"link": "", "note": ""},
    "lijst 7": {"link": "", "note": ""},
    "lijst 8": {"link": "", "note": ""},
    "lijst 9": {"link": "", "note": ""},
    "lijst 10": {"link": "", "note": ""},
}

EXCLUDE_LISTS = {
    "exclude 1": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/lists/3m6xfd6xs472o",
        "note": "EXCLUDE (nooit repost/like)",
    }
}

HASHTAG_QUERY = "#bskypromo"

# ============================================================
# FIXED SLOTS (unlimited + always refresh)
# - Slot 3: single promo post
# - Slot 4: random beautyfan
# - Slot 5: random Hotbleusky
# - Slot 6: random bleuskybeauty2
# ============================================================

SINGLE_PROMO_POST = "https://bsky.app/profile/beautygroup.bsky.social/post/3mcildeh7cs2r"
SLOT4_ACTOR = "beautyfan.bsky.social"
SLOT5_ACTOR = "Hotbleusky.bsky.social"
SLOT6_ACTOR = "bleuskybeauty2.bsky.social"

# ============================================================
# RUNTIME CONFIG (env)
# ============================================================
HOURS_BACK = int(os.getenv("HOURS_BACK", "3"))                 # normale candidates
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "100"))             # incl slots
MAX_PER_USER = int(os.getenv("MAX_PER_USER", "3"))             # alleen normale candidates
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "2"))

STATE_FILE = os.getenv("STATE_FILE", "repost_state_bleuskypromo.json")

LIST_MEMBER_LIMIT = int(os.getenv("LIST_MEMBER_LIMIT", "1500"))      # >= 1000
AUTHOR_POSTS_PER_MEMBER = int(os.getenv("AUTHOR_POSTS_PER_MEMBER", "10"))
FEED_MAX_ITEMS = int(os.getenv("FEED_MAX_ITEMS", "500"))
HASHTAG_MAX_ITEMS = int(os.getenv("HASHTAG_MAX_ITEMS", "100"))

SLOT_AUTHOR_FEED_LIMIT = int(os.getenv("SLOT_AUTHOR_FEED_LIMIT", "100"))

ENV_USERNAME = os.getenv("ENV_USERNAME", "BSKY_USERNAME_BP")
ENV_PASSWORD = os.getenv("ENV_PASSWORD", "BSKY_PASSWORD_BP")

# ============================================================
# REGEX
# ============================================================
FEED_URL_RE = re.compile(r"^https?://(www\.)?bsky\.app/profile/([^/]+)/feed/([^/?#]+)", re.I)
LIST_URL_RE = re.compile(r"^https?://(www\.)?bsky\.app/profile/([^/]+)/lists/([^/?#]+)", re.I)
POST_URL_RE = re.compile(r"^https?://(www\.)?bsky\.app/profile/([^/]+)/post/([^/?#]+)", re.I)


# ============================================================
# helpers
# ============================================================

def log(msg: str):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(post) -> Optional[datetime]:
    indexed = getattr(post, "indexedAt", None) or getattr(post, "indexed_at", None)
    if indexed:
        try:
            return datetime.fromisoformat(indexed.replace("Z", "+00:00"))
        except Exception:
            pass

    record = getattr(post, "record", None)
    if record:
        created = getattr(record, "createdAt", None) or getattr(record, "created_at", None)
        if created:
            try:
                return datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                pass
    return None


def is_quote_post(record) -> bool:
    embed = getattr(record, "embed", None)
    if not embed:
        return False
    return bool(getattr(embed, "record", None) or getattr(embed, "recordWithMedia", None))


def has_media(record) -> bool:
    """
    Alleen echte media: images/video.
    External-only (link cards) telt NIET als media.
    """
    embed = getattr(record, "embed", None)
    if not embed:
        return False

    if getattr(embed, "images", None):
        return True

    if getattr(embed, "video", None):
        return True

    if getattr(embed, "external", None):
        return False

    rwm = getattr(embed, "recordWithMedia", None)
    if rwm and getattr(rwm, "media", None):
        m = rwm.media
        if getattr(m, "images", None):
            return True
        if getattr(m, "video", None):
            return True

    return False


def resolve_handle_to_did(client: Client, actor: str) -> Optional[str]:
    if actor.startswith("did:"):
        return actor
    try:
        out = client.com.atproto.identity.resolve_handle({"handle": actor})
        return getattr(out, "did", None)
    except Exception:
        return None


def normalize_feed_uri(client: Client, s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if s.startswith("at://") and "/app.bsky.feed.generator/" in s:
        return s
    m = FEED_URL_RE.match(s)
    if not m:
        return None
    actor = m.group(2)
    rkey = m.group(3)
    did = resolve_handle_to_did(client, actor)
    if not did:
        return None
    return f"at://{did}/app.bsky.feed.generator/{rkey}"


def normalize_list_uri(client: Client, s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if s.startswith("at://") and "/app.bsky.graph.list/" in s:
        return s
    m = LIST_URL_RE.match(s)
    if not m:
        return None
    actor = m.group(2)
    rkey = m.group(3)
    did = resolve_handle_to_did(client, actor)
    if not did:
        return None
    return f"at://{did}/app.bsky.graph.list/{rkey}"


def normalize_post_uri(client: Client, s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if s.startswith("at://") and "/app.bsky.feed.post/" in s:
        return s
    m = POST_URL_RE.match(s)
    if not m:
        return None
    actor = m.group(2)
    rkey = m.group(3)
    did = resolve_handle_to_did(client, actor)
    if not did:
        return None
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def load_state(path: str) -> Dict:
    if not os.path.exists(path):
        return {"repost_records": {}, "like_records": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: Dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def parse_at_uri_rkey(uri: str) -> Optional[Tuple[str, str, str]]:
    if not uri or not uri.startswith("at://"):
        return None
    rest = uri[len("at://"):]
    parts = rest.split("/")
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]


def fetch_feed_items(client: Client, feed_uri: str, max_items: int) -> List:
    items: List = []
    cursor = None
    page = 0
    while True:
        page += 1
        if page == 1:
            log(f"   feed page {page} ...")
        params = {"feed": feed_uri, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        out = client.app.bsky.feed.get_feed(params)
        batch = getattr(out, "feed", []) or []
        items.extend(batch)
        cursor = getattr(out, "cursor", None)
        if not cursor or len(items) >= max_items:
            break
    return items[:max_items]


def fetch_list_members(client: Client, list_uri: str, limit: int) -> List[Tuple[str, str]]:
    members: List[Tuple[str, str]] = []
    cursor = None
    page = 0
    while True:
        page += 1
        if page == 1 or page % 10 == 0:
            log(f"   list page {page} (members so far: {len(members)})")
        params = {"list": list_uri, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        out = client.app.bsky.graph.get_list(params)
        items = getattr(out, "items", []) or []
        for it in items:
            subj = getattr(it, "subject", None)
            if not subj:
                continue
            h = (getattr(subj, "handle", "") or "").lower()
            d = (getattr(subj, "did", "") or "").lower()
            if h or d:
                members.append((h, d))
            if len(members) >= limit:
                return members[:limit]
        cursor = getattr(out, "cursor", None)
        if not cursor:
            break
    return members[:limit]


def fetch_author_feed(client: Client, actor: str, limit: int) -> List:
    try:
        out = client.app.bsky.feed.get_author_feed({"actor": actor, "limit": limit})
        return getattr(out, "feed", []) or []
    except Exception:
        return []


def fetch_hashtag_posts(client: Client, max_items: int) -> List:
    try:
        out = client.app.bsky.feed.search_posts({"q": HASHTAG_QUERY, "sort": "latest", "limit": max_items})
        return getattr(out, "posts", []) or []
    except Exception:
        return []


def get_postview_by_uri(client: Client, uri: str):
    try:
        out = client.app.bsky.feed.get_posts({"uris": [uri]})
        posts = getattr(out, "posts", []) or []
        return posts[0] if posts else None
    except Exception:
        return None


def build_candidates_from_feed_items(
    items: List,
    cutoff: datetime,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
) -> List[Dict]:
    cands: List[Dict] = []
    for item in items:
        post = getattr(item, "post", None)
        if not post:
            continue

        if hasattr(item, "reason") and item.reason is not None:
            continue

        record = getattr(post, "record", None)
        if not record:
            continue

        if getattr(record, "reply", None):
            continue

        if is_quote_post(record):
            continue

        if not has_media(record):
            continue

        uri = getattr(post, "uri", None)
        cid = getattr(post, "cid", None)
        if not uri or not cid:
            continue

        author = getattr(post, "author", None)
        ah = (getattr(author, "handle", "") or "").lower()
        ad = (getattr(author, "did", "") or "").lower()

        if ah in exclude_handles or ad in exclude_dids:
            continue

        created = parse_time(post)
        if not created or created < cutoff:
            continue

        cands.append({
            "uri": uri,
            "cid": cid,
            "created": created,
            "author_key": ad or ah or uri,
        })

    cands.sort(key=lambda x: x["created"])
    return cands


def build_candidates_from_postviews(
    posts: List,
    cutoff: datetime,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
) -> List[Dict]:
    cands: List[Dict] = []
    for post in posts:
        record = getattr(post, "record", None)
        if not record:
            continue

        if getattr(record, "reply", None):
            continue

        if is_quote_post(record):
            continue

        if not has_media(record):
            continue

        uri = getattr(post, "uri", None)
        cid = getattr(post, "cid", None)
        if not uri or not cid:
            continue

        author = getattr(post, "author", None)
        ah = (getattr(author, "handle", "") or "").lower()
        ad = (getattr(author, "did", "") or "").lower()

        if ah in exclude_handles or ad in exclude_dids:
            continue

        created = parse_time(post)
        if not created or created < cutoff:
            continue

        cands.append({
            "uri": uri,
            "cid": cid,
            "created": created,
            "author_key": ad or ah or uri,
        })

    cands.sort(key=lambda x: x["created"])
    return cands


def force_unrepost_unlike_if_needed(
    client: Client,
    me: str,
    subject_uri: str,
    repost_records: Dict[str, str],
    like_records: Dict[str, str],
):
    # unrepost
    if subject_uri in repost_records:
        existing_repost_uri = repost_records.get(subject_uri)
        parsed = parse_at_uri_rkey(existing_repost_uri) if existing_repost_uri else None
        if parsed:
            did, collection, rkey = parsed
            if did == me and collection == "app.bsky.feed.repost":
                try:
                    client.app.bsky.feed.repost.delete({"repo": me, "rkey": rkey})
                    log(f"🔁 refresh unrepost: {subject_uri}")
                except Exception as e_del:
                    log(f"⚠️ refresh unrepost failed: {e_del}")
        repost_records.pop(subject_uri, None)

    # unlike
    if subject_uri in like_records:
        existing_like_uri = like_records.get(subject_uri)
        parsed = parse_at_uri_rkey(existing_like_uri) if existing_like_uri else None
        if parsed:
            did, collection, rkey = parsed
            if did == me and collection == "app.bsky.feed.like":
                try:
                    client.app.bsky.feed.like.delete({"repo": me, "rkey": rkey})
                    log(f"💔 refresh unlike: {subject_uri}")
                except Exception as e_ul:
                    log(f"⚠️ refresh unlike failed: {e_ul}")
        like_records.pop(subject_uri, None)


def repost_and_like(
    client: Client,
    me: str,
    subject_uri: str,
    subject_cid: str,
    repost_records: Dict[str, str],
    like_records: Dict[str, str],
    force_refresh: bool,
) -> bool:
    if force_refresh:
        force_unrepost_unlike_if_needed(client, me, subject_uri, repost_records, like_records)

    try:
        out = client.app.bsky.feed.repost.create(
            repo=me,
            record={
                "subject": {"uri": subject_uri, "cid": subject_cid},
                "createdAt": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        repost_uri = getattr(out, "uri", None)
        if repost_uri:
            repost_records[subject_uri] = repost_uri
    except Exception as e:
        log(f"⚠️ repost error: {e}")
        return False

    try:
        out_like = client.app.bsky.feed.like.create(
            repo=me,
            record={
                "subject": {"uri": subject_uri, "cid": subject_cid},
                "createdAt": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        like_uri = getattr(out_like, "uri", None)
        if like_uri:
            like_records[subject_uri] = like_uri
    except Exception as e_like:
        log(f"⚠️ like error: {e_like}")

    return True


def pick_random_post_from_actor_unlimited(
    client: Client,
    actor: str,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
) -> Optional[Tuple[str, str]]:
    items = fetch_author_feed(client, actor, SLOT_AUTHOR_FEED_LIMIT)
    eligible: List[Tuple[str, str]] = []

    for item in items:
        post = getattr(item, "post", None)
        if not post:
            continue

        if hasattr(item, "reason") and item.reason is not None:
            continue

        record = getattr(post, "record", None)
        if not record:
            continue

        if getattr(record, "reply", None):
            continue

        if is_quote_post(record):
            continue

        if not has_media(record):
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

    if not eligible:
        return None

    return random.choice(eligible)


def main():
    log("main() entered")

    username = os.getenv(ENV_USERNAME, "").strip()
    password = os.getenv(ENV_PASSWORD, "").strip()
    if not username or not password:
        log(f"❌ Missing env {ENV_USERNAME} / {ENV_PASSWORD}")
        return

    cutoff = utcnow() - timedelta(hours=HOURS_BACK)
    log(f"Cutoff: {cutoff.isoformat()}  (HOURS_BACK={HOURS_BACK})")

    state = load_state(STATE_FILE)
    repost_records: Dict[str, str] = state.get("repost_records", {})
    like_records: Dict[str, str] = state.get("like_records", {})

    log("Logging in...")
    client = Client()
    client.login(username, password)
    me = client.me.did
    log(f"✅ Logged in as {me}")

    # ---- normalize feeds/lists ----
    feed_uris: List[Tuple[str, str, str]] = []
    for key, obj in FEEDS.items():
        link = (obj.get("link") or "").strip()
        note = (obj.get("note") or "").strip()
        if not link:
            continue
        uri = normalize_feed_uri(client, link)
        if uri:
            feed_uris.append((key, note, uri))
        else:
            log(f"⚠️ Feed ongeldig (skip): {key} -> {link}")

    list_uris: List[Tuple[str, str, str]] = []
    for key, obj in LIJSTEN.items():
        link = (obj.get("link") or "").strip()
        note = (obj.get("note") or "").strip()
        if not link:
            continue
        uri = normalize_list_uri(client, link)
        if uri:
            list_uris.append((key, note, uri))
        else:
            log(f"⚠️ Lijst ongeldig (skip): {key} -> {link}")

    excl_uris: List[Tuple[str, str, str]] = []
    for key, obj in EXCLUDE_LISTS.items():
        link = (obj.get("link") or "").strip()
        note = (obj.get("note") or "").strip()
        if not link:
            continue
        uri = normalize_list_uri(client, link)
        if uri:
            excl_uris.append((key, note, uri))
        else:
            log(f"⚠️ Exclude lijst ongeldig (skip): {key} -> {link}")

    # ---- exclude sets ----
    exclude_handles: Set[str] = set()
    exclude_dids: Set[str] = set()
    for key, note, luri in excl_uris:
        log(f"🚫 Loading exclude list: {key} ({note})")
        members = fetch_list_members(client, luri, limit=max(1000, LIST_MEMBER_LIMIT))
        log(f"🚫 Exclude members loaded: {len(members)}")
        for h, d in members:
            if h:
                exclude_handles.add(h.lower())
            if d:
                exclude_dids.add(d.lower())

    # ---- collect candidates (feeds + lists + hashtag) ----
    all_candidates: List[Dict] = []

    log(f"Feeds to process: {len(feed_uris)}")
    for key, note, furi in feed_uris:
        log(f"📥 Feed: {key} ({note})")
        items = fetch_feed_items(client, furi, max_items=FEED_MAX_ITEMS)
        all_candidates.extend(build_candidates_from_feed_items(items, cutoff, exclude_handles, exclude_dids))

    log(f"Lists to process: {len(list_uris)}")
    for key, note, luri in list_uris:
        log(f"📋 List: {key} ({note})")
        members = fetch_list_members(client, luri, 