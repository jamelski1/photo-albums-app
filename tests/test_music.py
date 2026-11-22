"""Unit tests for the procedural music library and the selection rule."""
import numpy as np
import pytest
from scipy.io import wavfile

import music


def test_track_profiles_have_expected_mode_and_tempo_order():
    calm = music.track_profile("calm")
    bright = music.track_profile("bright")
    dramatic = music.track_profile("dramatic")
    assert calm["major"] == 1.0
    assert dramatic["major"] == 0.0
    # BPM order in the library: bright 116, warm 94, dramatic 82, calm 72.
    warm = music.track_profile("warm")
    assert bright["tempo_norm"] > warm["tempo_norm"] > dramatic["tempo_norm"] > calm["tempo_norm"]
    for profile in (calm, bright, dramatic, music.track_profile("warm")):
        for value in profile.values():
            assert 0.0 <= value <= 1.0


def test_synth_track_is_finite_normalized_and_long_enough():
    audio = music.synth_track(music.TRACKS["calm"])
    assert len(audio) >= 40 * music.SR
    assert np.all(np.isfinite(audio))
    assert np.abs(audio).max() <= 0.72 + 1e-6
    assert np.abs(audio).max() > 0.5  # it actually makes sound


def test_ensure_tracks_writes_four_readable_wavs(tmp_path):
    music.ensure_tracks(tmp_path)
    for name in ("calm", "bright", "warm", "dramatic"):
        rate, data = wavfile.read(tmp_path / f"{name}.wav")
        assert rate == music.SR
        assert len(data) > 40 * music.SR


def _cluster(brightness, saturation, warmth, edge):
    return {"mean_brightness": brightness, "mean_saturation": saturation,
            "mean_warmth": warmth, "mean_edge_density": edge}


def test_choose_track_is_deterministic():
    clusters = [_cluster(0.3, 0.2, -0.05, 0.05), _cluster(0.8, 0.7, 0.1, 0.2)]
    first = music.choose_for_clusters(clusters)
    second = music.choose_for_clusters(clusters)
    assert first == second


def test_choose_track_scores_all_tracks_and_dark_cluster_prefers_dramatic():
    dark = _cluster(0.15, 0.1, -0.1, 0.03)
    bright = _cluster(0.9, 0.85, 0.12, 0.25)
    choices = music.choose_for_clusters([dark, bright])
    track, target, scores = choices[0]
    assert set(scores) == {"calm", "bright", "warm", "dramatic"}
    assert scores[track] == min(scores.values())
    _, _, bright_scores = choices[1]
    assert scores["dramatic"] < bright_scores["dramatic"]


def test_norm_helper():
    assert music._norm(5, 0, 10) == 0.5
    assert music._norm(-1, 0, 10) == 0.0
    assert music._norm(11, 0, 10) == 1.0
    assert music._norm(5, 5, 5) == 0.5
