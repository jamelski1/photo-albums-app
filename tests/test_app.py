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


def test_unknown_job_is_404(client):
    assert client.get("/job/doesnotexist").status_code == 404
    assert client.get("/job/doesnotexist/status.json").status_code == 404
