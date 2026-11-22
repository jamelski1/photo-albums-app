"""Jamendo music source: real Creative Commons tracks matched to a
collection by the same target profile the synthesizer rule produces.

The mapping is deliberate and auditable. The cluster's target profile
(tempo, mode, timbre, register, warmth, each 0..1) is turned into a
Jamendo query: a speed bucket from the tempo, and mood tags from the
mode and warmth. Candidates come back from the API and are scored
deterministically: speed distance, mood-tag overlap, and whether the
track may be downloaded. The winner's file is downloaded and its name,
artist, page, and licence are recorded for attribution.

Everything here degrades gracefully. With no JAMENDO_CLIENT_ID in the
environment, or on any network or API failure, callers get None and
fall back to the synthesized library in music.py.
"""
import json
import os
import urllib.parse
import urllib.request

API_URL = "https://api.jamendo.com/v3.0/tracks/"
TIMEOUT = 20

# Mood vocabularies kept small and close to the tags Jamendo artists
# actually use, so fuzzy tag matching has something to bite on.
BRIGHT_TAGS = ("happy", "uplifting", "energetic", "fun")
DARK_TAGS = ("melancholic", "dramatic", "emotional", "sad")
WARM_TAGS = ("warm", "acoustic", "folk")
COOL_TAGS = ("electronic", "ambient", "chill")


def client_id(env=None):
    env = os.environ if env is None else env
    return env.get("JAMENDO_CLIENT_ID") or None


def speed_bucket(tempo_norm):
    if tempo_norm >= 0.62:
        return "high"
    if tempo_norm >= 0.35:
        return "medium"
    return "low"


SPEED_ORDER = {"low": 0, "medium": 1, "high": 2}


def target_to_query(target):
    """Target profile -> (fuzzy tags, speed bucket) for the API call.
    The target uses music.choose_track's keys: tempo_norm, major,
    timbre, register_norm, warmth."""
    tags = list(BRIGHT_TAGS if target["major"] >= 0.5 else DARK_TAGS)
    tags += WARM_TAGS if target["warmth"] >= 0.5 else COOL_TAGS
    if target["tempo_norm"] >= 0.62:
        tags.append("energetic")
    elif target["tempo_norm"] < 0.35:
        tags.append("relaxing")
    return tags, speed_bucket(target["tempo_norm"])


def _default_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "photo-albums-app/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_tracks(tags, cid, limit=50, http_get=None):
    # Note: the API's speed filter is not used. Jamendo's speed metadata
    # is sparse (most tracks carry none), so filtering by it returns
    # almost nothing; speed is scored locally instead, when present.
    params = {
        "client_id": cid,
        "format": "json",
        "limit": limit,
        "fuzzytags": " ".join(tags),
        "include": "musicinfo+licenses",
        "order": "popularity_total",
        "vocalinstrumental": "instrumental",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    data = (http_get or _default_get)(url)
    if data.get("headers", {}).get("status") != "success":
        return []
    return data.get("results", [])


def score_candidate(track, want_tags, want_speed):
    """Lower is better. Deterministic in the track's own fields."""
    info = track.get("musicinfo", {}) or {}
    got_speed = info.get("speed") or ""
    speed_dist = abs(SPEED_ORDER.get(got_speed, 1) - SPEED_ORDER[want_speed])
    track_tags = set()
    tags = info.get("tags", {}) or {}
    for key in ("genres", "vartags", "instruments"):
        track_tags.update(t.lower() for t in tags.get(key, []) or [])
    overlap = len(track_tags.intersection(t.lower() for t in want_tags))
    downloadable = 0 if track.get("audiodownload_allowed") else 1
    return (speed_dist, -overlap, downloadable, int(track.get("id", 0)))


def pick_for_target(target, cid=None, http_get=None):
    """Best Jamendo track for one cluster target, or None to fall back."""
    cid = cid or client_id()
    if not cid:
        return None
    tags, speed = target_to_query(target)
    try:
        results = search_tracks(tags, cid, http_get=http_get)
        if not results:
            results = search_tracks(tags[:2], cid, http_get=http_get)
        if not results:
            results = search_tracks(tags[:1], cid, http_get=http_get)
    except Exception:
        return None
    if not results:
        return None
    best = min(results, key=lambda t: score_candidate(t, tags, speed))
    audio_url = best.get("audiodownload") if best.get("audiodownload_allowed") else best.get("audio")
    if not audio_url:
        return None
    licenses = best.get("licenses", {}) or {}
    return {
        "source": "jamendo",
        "track_id": int(best.get("id", 0)),
        "title": best.get("name", "Untitled"),
        "artist": best.get("artist_name", "Unknown artist"),
        "audio_url": audio_url,
        "page_url": f"https://www.jamendo.com/track/{best.get('id')}",
        "license_ccurl": licenses.get("ccurl") or best.get("license_ccurl", ""),
        "duration": best.get("duration"),
        "query_tags": tags,
        "query_speed": speed,
        "score": score_candidate(best, tags, speed)[:3],
    }


def download(audio_url, dest, http_open=None):
    """Download the track file; returns True on success."""
    try:
        if http_open is None:
            req = urllib.request.Request(audio_url, headers={"User-Agent": "photo-albums-app/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
                f.write(resp.read())
        else:
            http_open(audio_url, dest)
        return os.path.getsize(dest) > 10_000
    except Exception:
        return False
