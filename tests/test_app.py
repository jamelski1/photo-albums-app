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


def test_upload_error_is_json_for_the_page_uploader(client):
    resp = client.post("/upload", data={}, content_type="multipart/form-data",
                       headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 400
    assert resp.get_json()["error"].startswith("Please upload between")


def test_not_found_renders_a_page(client):
    resp = client.get("/job/doesnotexist")
    assert resp.status_code == 404
    assert b"Not found" in resp.data and b"Back to the start" in resp.data


def test_job_page_lists_every_pipeline_stage(client):
    app_module.JOBS_STATE["stagetest"] = {"state": "working", "step": "Starting"}
    try:
        resp = client.get("/job/stagetest")
    finally:
        del app_module.JOBS_STATE["stagetest"]
    assert resp.status_code == 200
    for _key, name in app_module.STAGES:
        assert name.encode() in resp.data
    assert b"/job/stagetest/status.json" in resp.data


def _result(jamendo):
    music = {"track": "calm", "source": "synth", "file": "calm.wav",
             "scores": {"calm": 0.2, "bright": 1.1, "warm": 0.6, "dramatic": 1.5},
             "target": {"tempo_norm": 0.1, "major": 0.6, "timbre": 0.2,
                        "register_norm": 0.4, "warmth": 0.5}}
    if jamendo:
        music.update({"track": "Golden Hour", "source": "jamendo", "file": "jamendo_cluster_0.mp3",
                      "artist": "Example Artist", "page_url": "https://www.jamendo.com/track/1",
                      "license_ccurl": "https://creativecommons.org/licenses/by/3.0/",
                      "query_tags": ["happy", "relaxing"], "query_speed": "low",
                      "synth_track": "calm"})
    return {"n_images": 9, "chosen_k": 1, "silhouette_by_k": {"1": 0.25},
            "clusters": [{"cluster": 0, "size": 9, "mean_brightness": 0.5,
                          "mean_saturation": 0.3, "mean_warmth": -0.1,
                          "mean_edge_density": 0.07, "dominant_colors": ["#112233"],
                          "montage": "montage_cluster_0.jpg",
                          "video": "slideshow_cluster_0.mp4", "music": music}]}


@pytest.mark.parametrize("jamendo", [False, True])
def test_results_page_renders_a_finished_job(client, tmp_path, monkeypatch, jamendo):
    import json

    monkeypatch.setattr(app_module, "JOBS", tmp_path)
    out = tmp_path / "job1" / "output"
    out.mkdir(parents=True)
    out.joinpath("result.json").write_text(json.dumps(_result(jamendo)))
    resp = client.get("/results/job1")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Collection 1" in html
    assert "/files/job1/output/slideshow_cluster_0.mp4" in html
    assert "Download video" in html
    if jamendo:
        assert "Golden Hour" in html and "Example Artist" in html
        assert "creativecommons.org/licenses/by/3.0/" in html
    else:
        assert "Synthesized in code" in html


def test_results_redirects_to_job_page_until_finished(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "JOBS", tmp_path)
    resp = client.get("/results/pending")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/job/pending")


def test_home_and_job_pages_carry_the_backdrop_with_credit(client):
    home = client.get("/").data.decode()
    assert 'class="backdrop"' in home
    assert "/static/backdrop/tetons.jpg" in home
    assert "Ansel Adams" in home and "commons.wikimedia.org" in home
    app_module.JOBS_STATE["bd"] = {"state": "working", "step": "Starting"}
    try:
        assert 'class="backdrop"' in client.get("/job/bd").data.decode()
    finally:
        del app_module.JOBS_STATE["bd"]


def test_backdrop_files_exist_for_every_credit():
    for photo in app_module.BACKDROP:
        assert (app_module.BASE / "static" / "backdrop" / photo["file"]).is_file()


def test_results_page_stays_plain(client, tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(app_module, "JOBS", tmp_path)
    out = tmp_path / "job2" / "output"
    out.mkdir(parents=True)
    out.joinpath("result.json").write_text(json.dumps(_result(False)))
    assert 'class="backdrop"' not in client.get("/results/job2").data.decode()
