"""Route-level tests for the Flask app (no pipeline run is triggered)."""
import io

import pytest
from PIL import Image

import app as app_module


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Automatic Photo Albums" in resp.data


def test_upload_rejects_too_few_photos(client):
    data = {"photos": [(io.BytesIO(_jpeg_bytes()), f"p{i}.jpg") for i in range(3)]}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_rejects_empty_submission(client):
    resp = client.post("/upload", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_example_route_starts_a_job(client, monkeypatch):
    monkeypatch.setattr(app_module, "_run_example_job", lambda job_id: None)
    resp = client.post("/example")
    assert resp.status_code == 302
    assert "/job/" in resp.headers["Location"]


def test_fetch_example_photos(tmp_path, monkeypatch):
    import csv

    src = tmp_path / "src.jpg"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(src)
    manifest = tmp_path / "manifest.csv"
    with open(manifest, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image_url"])
        writer.writerow([src.as_uri()])
        writer.writerow([src.as_uri()])
    monkeypatch.setattr(app_module, "EXAMPLE_MANIFEST", manifest)
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    assert app_module._fetch_example_photos(images_dir) == 2
    assert (images_dir / "photo_000.jpg").exists()
    assert (images_dir / "photo_001.jpg").exists()


def test_original_url_derivation():
    thumb = ("https://thumb.wikimedia.org/wikipedia/commons/thumb/8/88/"
             "Zagedan_Lakes.jpg/1920px-Zagedan_Lakes.jpg?utm_source=x")
    assert app_module._original_url(thumb) == (
        "https://upload.wikimedia.org/wikipedia/commons/8/88/Zagedan_Lakes.jpg")
    assert app_module._original_url("https://example.com/a.jpg") is None


def test_unknown_job_is_404(client):
    assert client.get("/job/doesnotexist").status_code == 404
    assert client.get("/job/doesnotexist/status.json").status_code == 404
