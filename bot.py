from atproto import Client
import os
import re
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Set, Tuple


# ============================================================
# CONFIG — vul hier je bronnen in (leeg = skip)
# ============================================================

FEEDS = {
    "feed 1": {"link": "", "note": "PROMO (bovenaan)"},
    "feed 2": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/feed/aaabjeu5724em",
        "note": "mentions",
    },
    "feed 3": {"link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/feed/aaae6jfc5w2oi", "note": "bleuskypromo feed"},
    "feed 4": {"link": "", "note": ""},
    "feed 5": {"link": "", "note": ""},
    "feed 6": {"link": "", "note": ""},
    "feed 7": {"link": "", "note": ""},
    "feed 8": {"link": "", "note": ""},
    "feed 9": {"link": "", "note": ""},
    "feed 10": {"link": "", "note": ""},
}

LIJSTEN = {
    "lijst 1": {"link": "", "note": "PROMO (bovenaan)"},
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

# Uitsluiten: iedereen uit deze lijst(en) nooit repost/like
EXCLUDE_LISTS = {
    "exclude 1": {
        "link": "https://bsky.app/profile/did:plc:jaka644beit3x4vmmg6yysw7/lists/3m6xfd6xs472o",
        "note": "EXCLUDE (nooit repost)",
    }
}

HASHTAG_QUERY = "#bskypromo"


# ============================================================
# RUNTIME CONFIG (via env)
# ============================================================
HOURS_BACK = int(os.getenv("HOURS_BACK", "3"))                 # laatste 3 uur
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "100"))             # 100 posts
MAX_PER_USER = int(os.getenv("MAX_PER_USER", "3"))             # max 3 per user
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "2"))         # 2 sec delay

# State file om reposts/likes te tracken (voor promo refresh)
STATE_FILE = os.getenv("STATE_FILE", "repost_state_bleuskypromo.json")

# Leden nalopen (minimaal 1000)
LIST_MEMBER_LIMIT = int(os.getenv("LIST_MEMBER_LIMIT", "1500"))      # >= 1000
AUTHOR_POSTS_PER_MEMBER = int(os.getenv("AUTHOR_POSTS_PER_MEMBER", "10"))
FEED_MAX_ITEMS = int(os.getenv("FEED_MAX_ITEMS", "500"))
HASHTAG_MAX_ITEMS = int(os.getenv("HASHTAG_MAX_ITEMS", "100"))

# Credentials env (jij hebt deze secrets al)
ENV_USERNAME = os.getenv("ENV_USERNAME", "BSKY_USERNAME_BP")
ENV_PASSWORD = os.getenv("ENV_PASSWORD", "BSKY_PASSWORD_BP")


# ============================================================
# helpers
# ============================================================

FEED_URL_RE = re.compile(r"^https?://(www\.)?bsky\.app/profile/([^/]+)/feed/([^/?#]+)", re.I)
LIST_URL_RE = re.compile(r"^https?://(www\.)?bsky\.app/profile/([^/]+)/lists/([^/?#]+)", re.I)

PROMO_FEED_KEY = "feed 1"
PROMO_LIST_KEY = "lijst 1"


def log(msg: str):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")


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

    # Link card is niet toegestaan als "media"
    if getattr(embed, "external", None):
        return False

    # recordWithMedia media-check (we skippen quotes elders, maar dit helpt bij modelvarianten)
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
    return parts[0], parts[1], parts[2]  # did, collection, rkey


def fetch_feed_items(client: Client, feed_uri: str, max_items: int) -> List:
    items: List = []
    cursor = None
    while True:
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
    while True:
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


def build_candidates_from_feed_items(
    items: List,
    cutoff: datetime,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
    promo_force_refresh: bool,
) -> List[Dict]:
    cands: List[Dict] = []
    for item in items:
        post = getattr(item, "post", None)
        if not post:
            continue

        # boosts/reposts overslaan
        if hasattr(item, "reason") and item.reason is not None:
            continue

        record = getattr(post, "record", None)
        if not record:
            continue

        # replies overslaan
        if getattr(record, "reply", None):
            continue

        # quotes overslaan
        if is_quote_post(record):
            continue

        # ✅ alleen media posts
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
            "force_refresh": promo_force_refresh,
        })

    cands.sort(key=lambda x: x["created"])
    return cands


def build_candidates_from_postviews(
    posts: List,
    cutoff: datetime,
    exclude_handles: Set[str],
    exclude_dids: Set[str],
    promo_force_refresh: bool,
) -> List[Dict]:
    cands: List[Dict] = []
    for post in posts:
        record = getattr(post, "record", None)
        if not record:
            continue

        # replies overslaan
        if getattr(record, "reply", None):
            continue

        # quotes overslaan
        if is_quote_post(record):
            continue

        # ✅ alleen media posts
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
            "force_refresh": promo_force_refresh,
        })

    cands.sort(key=lambda x: x["created"])
    return cands


def main():
    username = os.getenv(ENV_USERNAME, "").strip()
    password = os.getenv(ENV_PASSWORD, "").strip()
    if not username or not password:
        log(f"❌ Missing env {ENV_USERNAME} / {ENV_PASSWORD}")
        return

    cutoff = utcnow() - timedelta(hours=HOURS_BACK)

    state = load_state(STATE_FILE)
    repost_records: Dict[str, str] = state.get("repost_records", {})
    like_records: Dict[str, str] = state.get("like_records", {})

    client = Client()
    client.login(username, password)
    me = client.me.did
    log("✅ Logged in.")

    # ---- normalize feeds ----
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
            log(f"⚠️ Feed ongeldig (skip): {key}")

    # ---- normalize lists ----
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
            log(f"⚠️ Lijst ongeldig (skip): {key}")

    # ---- normalize exclude lists ----
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
            log(f"⚠️ Exclude lijst ongeldig (skip): {key}")

    # ---- build exclude sets ----
    exclude_handles: Set[str] = set()
    exclude_dids: Set[str] = set()
    for key, note, luri in excl_uris:
        log(f"🚫 Exclude lijst laden: {key}" + (f" ({note})" if note else ""))
        members = fetch_list_members(client, luri, limit=max(1000, LIST_MEMBER_LIMIT))
        log(f"🚫 Exclude leden: {len(members)}")
        for h, d in members:
            if h:
                exclude_handles.add(h.lower())
            if d:
                exclude_dids.add(d.lower())

    # ---- ORDER: promo feed 1 + promo lijst 1 eerst ----
    def promo_sort(item: Tuple[str, str, str], promo_key: str) -> int:
        return 0 if item[0] == promo_key else 1

    feed_uris.sort(key=lambda x: promo_sort(x, PROMO_FEED_KEY))
    list_uris.sort(key=lambda x: promo_sort(x, PROMO_LIST_KEY))

    all_candidates: List[Dict] = []

    # ---- FEEDS ----
    for key, note, furi in feed_uris:
        promo = (key == PROMO_FEED_KEY)
        label = f"{key}" + (f" ({note})" if note else "")
        log(f"📥 Feed verwerken: {label}" + (" [PROMO]" if promo else ""))
        items = fetch_feed_items(client, furi, max_items=FEED_MAX_ITEMS)
        all_candidates.extend(
            build_candidates_from_feed_items(items, cutoff, exclude_handles, exclude_dids, promo_force_refresh=promo)
        )

    # ---- LISTS (minimaal 1000 nalopen) ----
    for key, note, luri in list_uris:
        promo = (key == PROMO_LIST_KEY)
        label = f"{key}" + (f" ({note})" if note else "")
        log(f"📋 Lijst verwerken: {label}" + (" [PROMO]" if promo else ""))

        members = fetch_list_members(client, luri, limit=max(1000, LIST_MEMBER_LIMIT))
        log(f"👥 Leden opgehaald: {len(members)} (cap {max(1000, LIST_MEMBER_LIMIT)})")

        for (h, d) in members:
            actor = d or h
            if not actor:
                continue
            author_items = fetch_author_feed(client, actor, AUTHOR_POSTS_PER_MEMBER)
            all_candidates.extend(
                build_candidates_from_feed_items(author_items, cutoff, exclude_handles, exclude_dids, promo_force_refresh=promo)
            )

    # ---- HASHTAG (laatste 3 uur) ----
    log(f"🔎 Hashtag zoeken: {HASHTAG_QUERY} (last {HOURS_BACK}h)")
    hashtag_posts = fetch_hashtag_posts(client, HASHTAG_MAX_ITEMS)
    all_candidates.extend(
        build_candidates_from_postviews(hashtag_posts, cutoff, exclude_handles, exclude_dids, promo_force_refresh=False)
    )

    # ---- dedupe + sort (oudste eerst) ----
    seen: Set[str] = set()
    candidates: List[Dict] = []
    for c in sorted(all_candidates, key=lambda x: x["created"]):
        if c["uri"] in seen:
            continue
        seen.add(c["uri"])
        candidates.append(c)

    log(f"🧩 Candidates totaal: {len(candidates)} (na dedupe)")

    reposted = 0
    liked = 0
    per_user_count: Dict[str, int] = {}

    for c in candidates:
        if reposted >= MAX_PER_RUN:
            break

        ak = c["author_key"]
        per_user_count.setdefault(ak, 0)
        if per_user_count[ak] >= MAX_PER_USER:
            continue

        subject_uri = c["uri"]
        subject_cid = c["cid"]
        force = bool(c.get("force_refresh"))

        # PROMO refresh: unrepost + unlike indien nodig
        if force:
            # unrepost
            if subject_uri in repost_records:
                existing_repost_uri = repost_records.get(subject_uri)
                parsed = parse_at_uri_rkey(existing_repost_uri) if existing_repost_uri else None
                if parsed:
                    did, collection, rkey = parsed
                    if did == me and collection == "app.bsky.feed.repost":
                        try:
                            client.app.bsky.feed.repost.delete({"repo": me, "rkey": rkey})
                            log(f"🔁 PROMO unrepost: {subject_uri}")
                            repost_records.pop(subject_uri, None)
                        except Exception as e_del:
                            log(f"⚠️ PROMO unrepost failed: {e_del}")

            # unlike
            if subject_uri in like_records:
                existing_like_uri = like_records.get(subject_uri)
                parsed = parse_at_uri_rkey(existing_like_uri) if existing_like_uri else None
                if parsed:
                    did, collection, rkey = parsed
                    if did == me and collection == "app.bsky.feed.like":
                        try:
                            client.app.bsky.feed.like.delete({"repo": me, "rkey": rkey})
                            log(f"💔 PROMO unlike: {subject_uri}")
                            like_records.pop(subject_uri, None)
                        except Exception as e_ul:
                            log(f"⚠️ PROMO unlike failed: {e_ul}")

        # Als al gerepost en niet force refresh: skip
        if subject_uri in repost_records and not force:
            continue

        # ---- REPOST ----
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

            reposted += 1
            per_user_count[ak] += 1
            log(f"✅ Repost: {subject_uri}")

        except Exception as e:
            log(f"⚠️ Repost error: {e}")
            time.sleep(SLEEP_SECONDS)
            continue

        # ---- LIKE ----
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

            liked += 1
            log(f"❤️ Like: {subject_uri}")

        except Exception as e_like:
            log(f"⚠️ Like error: {e_like}")

        time.sleep(SLEEP_SECONDS)

    state["repost_records"] = repost_records
    state["like_records"] = like_records
    save_state(STATE_FILE, state)
    log(f"🔥 Done — {reposted} reposts, {liked} likes.")


if __name__ == "__main__":
    main()