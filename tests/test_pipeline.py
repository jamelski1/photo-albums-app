"""Unit tests for the analysis pipeline pieces that do not need the
ResNet-50 weights: visual statistics, k selection, and montage building."""
import numpy as np
from PIL import Image

import pipeline


def _save_solid(tmp_path, name, rgb, size=(200, 150)):
    path = tmp_path / name
    Image.new("RGB", size, rgb).save(path)
    return path


def test_visual_stats_white_is_bright_and_unsaturated(tmp_path):
    stats = pipeline.visual_stats(_save_solid(tmp_path, "w.jpg", (255, 255, 255)))
    assert stats["brightness"] > 0.99
    assert stats["saturation"] < 0.01
    assert len(stats["dominant_colors"]) == 3


def test_visual_stats_red_is_warm_and_blue_is_cool(tmp_path):
    red = pipeline.visual_stats(_save_solid(tmp_path, "r.jpg", (200, 40, 30)))
    blue = pipeline.visual_stats(_save_solid(tmp_path, "b.jpg", (30, 40, 200)))
    assert red["warmth"] > 0.3
    assert blue["warmth"] < -0.3


def test_visual_stats_checkerboard_has_more_edges_than_solid(tmp_path):
    board = Image.new("RGB", (200, 200), (0, 0, 0))
    px = board.load()
    for y in range(200):
        for x in range(200):
            if (x // 10 + y // 10) % 2:
                px[x, y] = (255, 255, 255)
    path = tmp_path / "board.jpg"
    board.save(path)
    solid = pipeline.visual_stats(_save_solid(tmp_path, "s.jpg", (120, 120, 120)))
    checkered = pipeline.visual_stats(path)
    assert checkered["edge_density"] > solid["edge_density"] + 0.05


def test_choose_k_recovers_three_blobs():
    rng = np.random.default_rng(7)
    centers = rng.normal(size=(3, 32))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    X = np.vstack([c + 0.05 * rng.normal(size=(15, 32)) for c in centers])
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    best_k, km, scores = pipeline.choose_k(X)
    assert best_k == 3
    assert set(scores) == {3, 4, 5, 6, 7, 8}
    assert len(km.labels_) == 45


def test_choose_k_respects_small_inputs():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(16, 16))
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    best_k, km, scores = pipeline.choose_k(X)
    assert 2 <= best_k <= 3  # k_hi = max(2, min(8, 16 // 5)) = 3
    assert len(km.labels_) == 16


def test_load_rgb_applies_exif_orientation(tmp_path):
    from PIL import Image

    p = tmp_path / "portrait.jpg"
    img = Image.new("RGB", (120, 80), (200, 30, 30))
    exif = img.getexif()
    exif[274] = 6  # stored landscape, meant to be shown rotated: portrait
    img.save(p, exif=exif)
    loaded = pipeline.load_rgb(p)
    assert loaded.size == (80, 120)


def test_build_montage_dimensions(tmp_path):
    paths = [_save_solid(tmp_path, f"p{i}.jpg", (i * 20 % 255, 80, 160)) for i in range(12)]
    out = tmp_path / "montage.jpg"
    pipeline.build_montage(paths, out)
    with Image.open(out) as img:
        assert img.size == (1280, 960)
