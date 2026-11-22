"""The photo album pipeline, adapted from the SENG 691 Assignment 5 system.

Steps, identical in method to the assignment version:
1. Visual statistics per photo (brightness, saturation, warmth, edge
   density, dominant colors).
2. ResNet-50 embeddings (ImageNet weights, classification head removed),
   L2-normalized.
3. K-Means clustering with k chosen by silhouette score.
4. A contact-sheet montage per cluster (12 images closest to the center).
5. Background music synthesized in code (see music.py) and chosen per
   cluster by the same weighted-distance rule as the assignment.
6. A slideshow video per cluster (ffmpeg), with the chosen track muxed in.
"""
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_rgb(path):
    """Open a photo as RGB with its EXIF orientation applied. Phone
    photos store portrait shots as landscape pixels plus an
    orientation tag; PIL ignores the tag, so without this step a
    portrait comes out sideways everywhere downstream."""
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")

import jamendo
import music

BATCH = 16
_model = None
_preprocess = None


def visual_stats(path):
    img = load_rgb(path)
    small = img.resize((128, 128))
    arr = np.asarray(small).astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx, mn = arr.max(axis=2), arr.min(axis=2)
    brightness = float(mx.mean())
    saturation = float((((mx - mn) / np.maximum(mx, 1e-6))[mx > 0]).mean()) if (mx > 0).any() else 0.0
    warmth = float(r.mean() - b.mean())
    gray = arr.mean(axis=2)
    gx = np.abs(np.diff(gray, axis=1)).mean()
    gy = np.abs(np.diff(gray, axis=0)).mean()
    edge_density = float(gx + gy)
    from sklearn.cluster import KMeans

    pixels = arr.reshape(-1, 3)[::37]
    km = KMeans(n_clusters=3, n_init=4, random_state=0).fit(pixels)
    dom = []
    for center in km.cluster_centers_:
        rgb = tuple(int(round(c * 255)) for c in center)
        dom.append("#%02x%02x%02x" % rgb)
    return {
        "brightness": round(brightness, 4),
        "saturation": round(saturation, 4),
        "warmth": round(warmth, 4),
        "edge_density": round(edge_density, 4),
        "dominant_colors": dom,
    }


def _load_model():
    global _model, _preprocess
    if _model is None:
        import torch
        from torchvision import models

        weights = models.ResNet50_Weights.IMAGENET1K_V2
        model = models.resnet50(weights=weights)
        model.fc = torch.nn.Identity()
        model.eval()
        _model = model
        _preprocess = weights.transforms()
    return _model, _preprocess


def extract_embeddings(paths, progress=None):
    import torch

    model, preprocess = _load_model()
    feats = []
    with torch.no_grad():
        for i in range(0, len(paths), BATCH):
            batch = [preprocess(load_rgb(p)) for p in paths[i : i + BATCH]]
            feats.append(model(torch.stack(batch)).numpy())
            if progress:
                progress(f"Reading photo features: {min(i + BATCH, len(paths))} of {len(paths)}")
    X = np.vstack(feats)
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def choose_k(X):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = len(X)
    k_hi = max(2, min(8, n // 5))
    k_lo = 2 if n < 40 else 3
    if k_hi <= k_lo:
        km = KMeans(n_clusters=k_lo, n_init=10, random_state=42).fit(X)
        return k_lo, km, {}
    scores = {}
    fits = {}
    for k in range(k_lo, k_hi + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        scores[k] = float(silhouette_score(X, km.labels_))
        fits[k] = km
    best_k = max(scores, key=scores.get)
    return best_k, fits[best_k], scores


def build_montage(paths, out_path):
    thumbs = []
    for p in paths:
        t = load_rgb(p)
        t.thumbnail((320, 320))
        thumbs.append(t)
    cols = 4
    rows = int(np.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (320 * cols, 320 * rows), "white")
    for j, t in enumerate(thumbs):
        sheet.paste(t, ((j % cols) * 320, (j // cols) * 320))
    sheet.save(out_path, quality=88)


def ffmpeg_bin():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def build_slideshow(image_paths, audio_path, out_path, progress=None,
                    beat_info=None):
    """Each photo becomes a segment on a blurred-fill 1280x720 canvas
    with fades, segments are concatenated, and the cluster's music
    track is muxed in with a fade out at the end. Without beat info
    every photo gets the fixed 2.6 s of the original recipe. With
    beat info (from beats.analyze), each photo gets a whole number of
    beats and every fade is centered on a beat: the fade out of one
    photo and the fade in of the next meet exactly on the beat grid,
    so the picture changes on the beat."""
    import tempfile

    ff = ffmpeg_bin()

    def run(cmd):
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    if beat_info:
        import beats
        durations, _ = beats.plan_segments(len(image_paths), beat_info)
        half = min(0.5, max(0.2, beat_info["period"] / 2.0))
    else:
        durations = [2.6] * len(image_paths)
        half = 0.4
    total_seconds = sum(durations)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        segs = []
        for i, p in enumerate(image_paths):
            seg = td / f"seg_{i:02d}.mp4"
            d = durations[i]
            out_st = max(0.0, d - half)
            vf = ("[0:v]scale=1280:720:force_original_aspect_ratio=increase,"
                  "crop=1280:720,boxblur=24:6[bg];"
                  "[0:v]scale=1280:720:force_original_aspect_ratio=decrease[fg];"
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
                  f"fade=t=in:st=0:d={half:.3f},"
                  f"fade=t=out:st={out_st:.3f}:d={half:.3f},format=yuv420p")
            run([ff, "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", str(p),
                 "-filter_complex", vf, "-r", "30", "-c:v", "libx264",
                 "-preset", "veryfast", "-crf", "22", str(seg)])
            segs.append(seg)
            if progress:
                progress(f"Building slideshow: clip {i + 1} of {len(image_paths)}")
        (td / "list.txt").write_text("".join(f"file '{s}'\n" for s in segs))
        run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(td / "list.txt"),
             "-c", "copy", str(td / "joined.mp4")])
        fade_start = max(0.0, total_seconds - 2.0)
        run([ff, "-y", "-i", str(td / "joined.mp4"),
             "-stream_loop", "-1", "-i", str(audio_path),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-af", f"afade=t=out:st={fade_start:.1f}:d=2", "-shortest",
             str(out_path)])
    if beat_info:
        return {"bpm": beat_info["bpm"], "period": beat_info["period"],
                "offset": beat_info["offset"],
                "durations": durations}
    return None


def run_pipeline(job_dir, progress):
    job_dir = Path(job_dir)
    images_dir = job_dir / "images"
    out_dir = job_dir / "output"
    out_dir.mkdir(exist_ok=True)
    paths = sorted(p for p in images_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if len(paths) < 8:
        raise ValueError("Please upload at least 8 photos.")

    progress("Measuring color and texture in every photo")
    stats = [visual_stats(p) for p in paths]

    progress("Reading photo features with ResNet-50")
    X = extract_embeddings(paths, progress)

    progress("Grouping the photos into collections")
    best_k, km, sil_scores = choose_k(X)
    labels = km.labels_
    centers = km.cluster_centers_
    centers = centers / np.linalg.norm(centers, axis=1, keepdims=True)
    dists = 1 - X @ centers.T

    stat_keys = ("brightness", "saturation", "warmth", "edge_density")
    clusters = []
    for c in range(best_k):
        idx = np.where(labels == c)[0]
        order = idx[np.argsort(dists[idx, c])]
        info = {
            "cluster": int(c),
            "size": int(len(idx)),
            "members": [paths[i].name for i in idx],
            "exemplars": [paths[i].name for i in order[:5]],
        }
        for key in stat_keys:
            info[f"mean_{key}"] = round(float(np.mean([stats[i][key] for i in idx])), 4)
        color_counts = Counter()
        for i in idx:
            color_counts.update(stats[i]["dominant_colors"])
        info["dominant_colors"] = [c for c, _ in color_counts.most_common(3)]
        clusters.append(info)

    progress("Composing the collection covers")
    for info in clusters:
        c = info["cluster"]
        idx = np.where(labels == c)[0]
        order = idx[np.argsort(dists[idx, c])]
        build_montage([paths[i] for i in order[:12]], out_dir / f"montage_cluster_{c}.jpg")

    progress("Scoring music for each collection")
    music_dir = Path(music.ensure_tracks(job_dir / "music"))
    choices = music.choose_for_clusters(clusters)
    for info in clusters:
        c = info["cluster"]
        track, target, scores = choices[c]
        entry = {"track": track, "source": "synth", "file": f"{track}.wav",
                 "scores": scores,
                 "target": {k: round(v, 3) for k, v in target.items()}}
        pick = jamendo.pick_for_target(target)
        if pick is not None:
            dest = music_dir / f"jamendo_cluster_{c}.mp3"
            if jamendo.download(pick["audio_url"], dest):
                entry.update(pick)
                entry["track"] = pick["title"]
                entry["file"] = dest.name
                entry["synth_track"] = track
        info["music"] = entry

    for info in clusters:
        c = info["cluster"]
        progress(f"Building the slideshow for collection {c + 1} of {best_k}")
        idx = np.where(labels == c)[0]
        order = idx[np.argsort(dists[idx, c])]
        members = [paths[i] for i in order[:12]]
        audio_file = music_dir / info["music"]["file"]
        import beats
        beat_info = beats.analyze(audio_file)
        timing = build_slideshow(members, audio_file,
                                 out_dir / f"slideshow_cluster_{c}.mp4",
                                 beat_info=beat_info)
        if timing:
            info["timing"] = timing
        info["video"] = f"slideshow_cluster_{c}.mp4"
        info["montage"] = f"montage_cluster_{c}.jpg"

    result = {
        "n_images": len(paths),
        "chosen_k": int(best_k),
        "silhouette_by_k": {int(k): round(v, 4) for k, v in sil_scores.items()},
        "clusters": clusters,
    }
    with open(out_dir / "result.json", "w") as f:
        json.dump(result, f, indent=2)
    progress("Done")
    return result
