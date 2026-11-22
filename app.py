"""Automatic Photo Albums: upload photos, get collections, covers, music
and slideshow videos, using the SENG 691 Assignment 5 pipeline."""
import json
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory, url_for
from PIL import Image

try:  # iPhone photos arrive as HEIC; convert them at intake when possible.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_OK = True
except Exception:
    HEIC_OK = False

BASE = Path(__file__).resolve().parent
JOBS = BASE / "jobs"
JOBS.mkdir(exist_ok=True)
MAX_PHOTOS = 60

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024

JOBS_STATE = {}

HOME = """
<!doctype html><title>Automatic Photo Albums</title>
<style>body{font-family:system-ui;margin:2rem auto;max-width:44rem;padding:0 1rem;line-height:1.5}
.drop{border:2px dashed #888;border-radius:12px;padding:2rem;text-align:center}
button{font-size:1rem;padding:.6rem 1.2rem;border-radius:8px}</style>
<h1>Automatic Photo Albums</h1>
<p>Upload a set of photos and the system will group similar photos into
collections, build a cover sheet for each one, compose background music
chosen by a rule from each collection's colors and detail, and generate a
slideshow video for every collection.</p>
<p>It uses a pre-trained ResNet-50 to understand the photos and K-Means to
group them, the same method as the SENG 691 Assignment 5 system.</p>
<form action="/upload" method="post" enctype="multipart/form-data">
  <div class="drop">
    <input type="file" name="photos" accept="image/*" multiple required>
    <p>Between 8 and 60 photos. JPG, PNG, WebP{% if heic %} and HEIC{% endif %}.</p>
    <button type="submit">Make my albums</button>
  </div>
</form>
"""

JOB_PAGE = """
<!doctype html><title>Working…</title>
<style>body{font-family:system-ui;margin:2rem auto;max-width:44rem;padding:0 1rem}</style>
<h1>Making your albums</h1>
<p id="step">Starting…</p>
<script>
async function poll(){
  const r = await fetch("/job/{{ job_id }}/status.json");
  const s = await r.json();
  if(s.state === "done"){ window.location = "/results/{{ job_id }}"; return; }
  if(s.state === "error"){ document.getElementById("step").textContent = "Something went wrong: " + s.step; return; }
  document.getElementById("step").textContent = s.step;
  setTimeout(poll, 2000);
}
poll();
</script>
"""

RESULTS = """
<!doctype html><title>Your albums</title>
<style>body{font-family:system-ui;margin:2rem auto;max-width:60rem;padding:0 1rem;line-height:1.5}
.cluster{border:1px solid #ddd;border-radius:12px;padding:1rem;margin:1.5rem 0}
img.cover{max-width:100%;border-radius:8px} video{max-width:100%;border-radius:8px}
.swatch{display:inline-block;width:1.1rem;height:1.1rem;border-radius:4px;border:1px solid #999;vertical-align:middle}
</style>
<h1>Your albums</h1>
<p>{{ result.n_images }} photos grouped into {{ result.chosen_k }} collections.</p>
{% for c in result.clusters %}
<div class="cluster">
  <h2>Collection {{ c.cluster + 1 }}: {{ c.size }} photos</h2>
  <img class="cover" src="/files/{{ job_id }}/output/{{ c.montage }}" alt="cover sheet">
  <p>Colors:
  {% for col in c.dominant_colors %}<span class="swatch" style="background:{{ col }}"></span> {{ col }} {% endfor %}
  </p>
  <p>Brightness {{ "%.2f"|format(c.mean_brightness) }}, saturation {{ "%.2f"|format(c.mean_saturation) }},
     warmth {{ "%+.2f"|format(c.mean_warmth) }}, detail {{ "%.3f"|format(c.mean_edge_density) }}.</p>
  <p><strong>Music: {{ c.music.track }}</strong>, chosen by the scoring rule
     (tempo from detail, brightness and tone from color).</p>
  <p><audio controls src="/files/{{ job_id }}/music/{{ c.music.track }}.wav"></audio></p>
  <video controls src="/files/{{ job_id }}/output/{{ c.video }}"></video>
</div>
{% endfor %}
<p><a href="/">Make another album</a></p>
"""


def _set_step(job_id, step):
    JOBS_STATE[job_id] = {"state": "working", "step": step}


def _run_job(job_id):
    import pipeline

    job_dir = JOBS / job_id
    try:
        pipeline.run_pipeline(job_dir, lambda s: _set_step(job_id, s))
        JOBS_STATE[job_id] = {"state": "done", "step": "Done"}
    except Exception as exc:  # surfaced on the job page
        JOBS_STATE[job_id] = {"state": "error", "step": str(exc)}


@app.route("/")
def home():
    return render_template_string(HOME, heic=HEIC_OK)


@app.route("/upload", methods=["POST"])
def upload():
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not (8 <= len(files) <= MAX_PHOTOS):
        return f"Please upload between 8 and {MAX_PHOTOS} photos.", 400
    job_id = uuid.uuid4().hex[:12]
    images_dir = JOBS / job_id / "images"
    images_dir.mkdir(parents=True)
    saved = 0
    for f in files:
        raw = images_dir / f"raw_{saved:03d}{Path(f.filename).suffix.lower()}"
        f.save(raw)
        try:
            img = Image.open(raw).convert("RGB")
            img.save(images_dir / f"photo_{saved:03d}.jpg", quality=92)
            saved += 1
        except Exception:
            pass
        raw.unlink(missing_ok=True)
    if saved < 8:
        return "Too few readable photos in that upload.", 400
    JOBS_STATE[job_id] = {"state": "working", "step": "Starting"}
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return redirect(url_for("job_page", job_id=job_id))


@app.route("/job/<job_id>")
def job_page(job_id):
    if job_id not in JOBS_STATE and not (JOBS / job_id).exists():
        abort(404)
    return render_template_string(JOB_PAGE, job_id=job_id)


@app.route("/job/<job_id>/status.json")
def job_status(job_id):
    state = JOBS_STATE.get(job_id)
    if state is None:
        if (JOBS / job_id / "output" / "result.json").exists():
            return {"state": "done", "step": "Done"}
        abort(404)
    return state


@app.route("/results/<job_id>")
def results(job_id):
    result_path = JOBS / job_id / "output" / "result.json"
    if not result_path.exists():
        return redirect(url_for("job_page", job_id=job_id))
    result = json.loads(result_path.read_text())
    return render_template_string(RESULTS, result=result, job_id=job_id)


@app.route("/files/<job_id>/<path:rel>")
def files(job_id, rel):
    return send_from_directory(JOBS / job_id, rel)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
