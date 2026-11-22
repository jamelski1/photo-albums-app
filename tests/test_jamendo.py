"""Unit tests for the Jamendo source: query mapping, candidate scoring,
and the graceful fallbacks. No network: the HTTP layer is faked."""
import jamendo


def _target(tempo=0.8, mode=0.9, timbre=0.5, register=0.5, warmth=0.8):
    # Keys match music.choose_track's target exactly.
    return {"tempo_norm": tempo, "major": mode, "timbre": timbre,
            "register_norm": register, "warmth": warmth}


def test_speed_buckets():
    assert jamendo.speed_bucket(0.9) == "high"
    assert jamendo.speed_bucket(0.5) == "medium"
    assert jamendo.speed_bucket(0.1) == "low"


def test_query_mapping_bright_fast_warm():
    tags, speed = jamendo.target_to_query(_target())
    assert speed == "high"
    assert "happy" in tags and "warm" in tags and "energetic" in tags


def test_query_mapping_dark_slow_cool():
    tags, speed = jamendo.target_to_query(_target(tempo=0.1, mode=0.1, warmth=0.1))
    assert speed == "low"
    assert "melancholic" in tags and "electronic" in tags and "relaxing" in tags


def _track(tid, speed, vartags, downloadable=True):
    return {"id": tid, "name": f"Track {tid}", "artist_name": "Artist",
            "audio": f"https://cdn.example/{tid}.mp3",
            "audiodownload": f"https://cdn.example/{tid}-dl.mp3",
            "audiodownload_allowed": downloadable, "duration": 120,
            "licenses": {"ccurl": "https://creativecommons.org/licenses/by/4.0/"},
            "musicinfo": {"speed": speed, "tags": {"genres": [], "vartags": vartags,
                                                   "instruments": []}}}


def _fake_get(payload):
    def get(url):
        assert "client_id=test" in url
        return payload
    return get


def test_pick_prefers_speed_and_tag_match_and_is_deterministic():
    payload = {"headers": {"status": "success"},
               "results": [_track(9, "low", ["sad"]),
                           _track(5, "high", ["energetic", "happy"]),
                           _track(7, "high", ["energetic"])]}
    pick = jamendo.pick_for_target(_target(), cid="test", http_get=_fake_get(payload))
    assert pick["track_id"] == 5
    assert pick["audio_url"].endswith("-dl.mp3")
    again = jamendo.pick_for_target(_target(), cid="test", http_get=_fake_get(payload))
    assert again == pick
    assert pick["page_url"] == "https://www.jamendo.com/track/5"


def test_pick_none_without_client_id(monkeypatch):
    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    assert jamendo.pick_for_target(_target()) is None


def test_pick_none_on_api_failure_and_empty_results():
    def boom(url):
        raise ConnectionError("offline")
    assert jamendo.pick_for_target(_target(), cid="test", http_get=boom) is None
    empty = {"headers": {"status": "success"}, "results": []}
    assert jamendo.pick_for_target(_target(), cid="test", http_get=_fake_get(empty)) is None


def test_download_size_check(tmp_path):
    dest = tmp_path / "t.mp3"
    assert jamendo.download("https://x", dest, http_open=lambda u, d: open(d, "wb").write(b"x" * 100)) is False
    assert jamendo.download("https://x", dest, http_open=lambda u, d: open(d, "wb").write(b"x" * 20000)) is True

    def boom(u, d):
        raise ConnectionError("offline")
    assert jamendo.download("https://x", dest, http_open=boom) is False
