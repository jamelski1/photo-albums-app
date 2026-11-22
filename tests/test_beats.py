"""Unit tests for beat analysis and beat-aligned segment planning.
Audio fixtures are synthesized: click tracks and a kick/hat loop at
known tempos, so the recovered grid can be checked against truth."""
import numpy as np
from scipy.io import wavfile

import beats

SR = beats.SR


def _write(tmp_path, samples, name="track.wav"):
    path = tmp_path / name
    wavfile.write(path, SR, (np.clip(samples, -1, 1) * 32767).astype(np.int16))
    return path


def _click_track(bpm, seconds=30, offset=0.13):
    n = int(SR * seconds)
    x = np.random.default_rng(7).normal(0, 0.004, n).astype(np.float64)
    period = 60.0 / bpm
    t = offset
    while t < seconds - 0.1:
        i = int(t * SR)
        x[i:i + 220] += np.hanning(220) * 0.9
        t += period
    return x, period, offset


def _kick_hat_track(bpm, seconds=30):
    n = int(SR * seconds)
    x = np.zeros(n)
    period = 60.0 / bpm
    t = 0.0
    while t < seconds - 0.3:
        i = int(t * SR)
        decay = np.exp(-np.arange(2600) / 500.0)
        x[i:i + 2600] += np.sin(2 * np.pi * 55 * np.arange(2600) / SR) * decay * 0.8
        j = int((t + period / 2) * SR)
        if j + 800 < n:
            x[j:j + 800] += np.random.default_rng(3).normal(0, 0.25, 800) * np.exp(-np.arange(800) / 200.0)
        t += period
    return x


def test_click_track_tempo_and_phase(tmp_path):
    x, period, offset = _click_track(120)
    info = beats.analyze(_write(tmp_path, x))
    assert info is not None
    assert abs(info["bpm"] - 120) <= 3
    phase_err = abs((info["offset"] - offset) % period)
    phase_err = min(phase_err, period - phase_err)
    assert phase_err < 0.06


def test_click_track_slower_tempo(tmp_path):
    x, _, _ = _click_track(84)
    info = beats.analyze(_write(tmp_path, x))
    assert info is not None
    assert abs(info["bpm"] - 84) <= 3


def test_kick_hat_tempo(tmp_path):
    info = beats.analyze(_write(tmp_path, _kick_hat_track(96)))
    assert info is not None
    assert abs(info["bpm"] - 96) <= 4


def test_silence_has_no_beats(tmp_path):
    info = beats.analyze(_write(tmp_path, np.zeros(SR * 10)))
    assert info is None


def test_plan_segments_boundaries_on_grid():
    info = {"bpm": 120.0, "period": 0.5, "offset": 0.2}
    durations, transitions = beats.plan_segments(6, info)
    assert len(durations) == 6 and len(transitions) == 5
    for t in transitions:
        assert abs((t - 0.2) % 0.5) < 1e-6
    assert all(1.9 <= d <= 3.1 for d in durations)
    again, _ = beats.plan_segments(6, info)
    assert again == durations
