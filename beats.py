"""Beat analysis for slideshow timing, with numpy only.

The slideshow builder used to give every photo a fixed 2.6 seconds,
so the fades between photos landed wherever they landed relative to
the music. This module measures the chosen track instead: it decodes
the audio, builds a spectral-flux onset envelope, estimates the tempo
by autocorrelation, and aligns a beat grid to the strongest onsets.
The builder then gives each photo a whole number of beats and puts
the midpoint of every fade exactly on a beat.

Everything degrades gracefully: any failure returns None and the
builder falls back to the fixed timing.
"""
import subprocess

import numpy as np

SR = 22050
HOP = 512
FRAME = 2048
MIN_BPM, MAX_BPM = 40.0, 200.0


def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_mono(audio_path, seconds=90):
    """Decode the first `seconds` of audio to mono float samples."""
    cmd = [_ffmpeg(), "-v", "error", "-i", str(audio_path),
           "-t", str(seconds), "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def onset_envelope(samples):
    """Spectral flux: per-frame sum of positive magnitude increases."""
    if len(samples) < FRAME * 2:
        return np.array([]), 0.0
    windows = np.lib.stride_tricks.sliding_window_view(samples, FRAME)[::HOP]
    mags = np.abs(np.fft.rfft(windows * np.hanning(FRAME), axis=1))
    flux = np.clip(np.diff(mags, axis=0), 0, None).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    peak = flux.max()
    if peak <= 0:
        return np.array([]), 0.0
    return flux / peak, SR / HOP


def estimate_period_frames(env, fps):
    """Autocorrelation tempo estimate, returned as a fractional frame
    count per beat, or None when nothing periodic stands out."""
    env = env - env.mean()
    corr = np.correlate(env, env, mode="full")[len(env) - 1:]
    lo = int(fps * 60.0 / MAX_BPM)
    hi = int(fps * 60.0 / MIN_BPM)
    if hi <= lo or len(corr) <= hi:
        return None
    # A gentle tempo prior centered on 120 BPM (a 0.5 s period).
    # A steady beat correlates almost as well at twice its period as
    # at the period itself, and the prior breaks that tie toward the
    # musically natural tempo instead of the half-time one.
    lags = np.arange(lo, hi)
    prior = np.exp(-0.5 * (np.log2((lags / fps) / 0.5) / 0.9) ** 2)
    weighted = corr[lo:hi] * prior
    lag = lo + int(np.argmax(weighted))
    if corr[lag] <= 0:
        return None
    # Parabolic refinement around the peak for a fractional lag.
    if 0 < lag < len(corr) - 1:
        a, b, c = corr[lag - 1], corr[lag], corr[lag + 1]
        denom = a - 2 * b + c
        if denom != 0:
            lag = lag + 0.5 * (a - c) / denom
    return float(lag)


def grid_offset(env, period_frames):
    """Phase of the beat grid: the offset (in frames) whose grid lines
    collect the most onset energy."""
    smoothed = np.convolve(env, np.ones(3), mode="same")
    best_off, best_score = 0.0, -1.0
    off = 0.0
    while off < period_frames:
        idx = np.arange(off, len(env), period_frames).astype(int)
        score = float(smoothed[idx].sum()) if len(idx) else 0.0
        if score > best_score:
            best_off, best_score = off, score
        off += 0.25
    return best_off


def refine_offset(samples, period, offset):
    """Snap the coarse grid to the actual attacks. The spectral
    envelope's peaks lag the true onsets by a fraction of the analysis
    window, so each beat is matched to the nearest strong onset in a
    fine time-domain envelope and the grid shifts by the median
    residual."""
    if len(samples) < SR:
        return offset
    win, hop = 512, 128
    hp = samples - np.convolve(samples, np.ones(64) / 64, mode="same")
    windows = np.lib.stride_tricks.sliding_window_view(hp, win)[::hop]
    energy = (windows ** 2).mean(axis=1)
    flux = np.clip(np.diff(energy), 0, None)
    if len(flux) == 0 or flux.max() <= 0:
        return offset
    times = (np.arange(len(flux)) * hop + win / 2) / SR
    duration = len(samples) / SR
    residuals = []
    t = offset
    while t < duration - 0.5:
        lo = np.searchsorted(times, t - 0.35 * period)
        hi = np.searchsorted(times, t + 0.35 * period)
        if hi > lo:
            peak_t = times[lo + int(np.argmax(flux[lo:hi]))]
            residuals.append(peak_t - t)
        t += period
    if not residuals:
        return offset
    return float((offset + np.median(residuals)) % period)


def analyze(audio_path):
    """Return {"bpm", "period", "offset"} for the track's beat grid
    (period and offset in seconds), or None when no reliable grid
    exists. The first beat at or after time 0 is at `offset`."""
    try:
        samples = decode_mono(audio_path)
        env, fps = onset_envelope(samples)
        if len(env) == 0:
            return None
        period_frames = estimate_period_frames(env, fps)
        if period_frames is None:
            return None
        period = period_frames / fps
        bpm = 60.0 / period
        if not (MIN_BPM - 5 <= bpm <= MAX_BPM + 5):
            return None
        offset = grid_offset(env, period_frames) / fps
        offset = refine_offset(samples, period, offset)
        return {"bpm": round(float(bpm), 1),
                "period": round(float(period), 4),
                "offset": round(float(offset), 4)}
    except Exception:
        return None


def plan_segments(n_photos, beat_info, target_seconds=2.6):
    """Per-photo durations (seconds) whose boundaries sit on beats.

    Each photo gets a whole number of beats close to target_seconds;
    the first boundary absorbs the grid offset, so every transition
    time is offset + k * period. Returns (durations, transitions).
    """
    period = beat_info["period"]
    offset = beat_info["offset"] % period
    beats = int(min(8, max(2, round(target_seconds / period))))
    boundaries = []
    k = beats
    while len(boundaries) < n_photos - 1:
        boundaries.append(offset + k * period)
        k += beats
    end = offset + (n_photos - 1) * beats * period + beats * period
    # If the offset pushed the first photo too long, the formula above
    # already keeps it within one beat of the others; durations:
    durations, prev = [], 0.0
    for b in boundaries + [end]:
        durations.append(round(b - prev, 3))
        prev = b
    transitions = [round(b, 3) for b in boundaries]
    return durations, transitions
