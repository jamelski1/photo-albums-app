"""Automatic Photo Albums: upload photos, get collections, covers, music
and slideshow videos, using the SENG 691 Assignment 5 pipeline."""
import json
import threading
import uuid
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from jinja2 import DictLoader
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
MIN_PHOTOS = 8
MAX_PHOTOS = 60

JOBS_STATE = {}

# The pipeline's progress messages start with these words; the job page
# uses them to light up the matching stage.
STAGES = [
    ("Measuring", "Measuring color and texture in every photo"),
    ("Reading", "Reading photo features with ResNet-50"),
    ("Grouping", "Grouping the photos into collections"),
    ("Composing", "Composing the collection covers"),
    ("Scoring", "Scoring music for each collection"),
    ("Building", "Building a slideshow video for each collection"),
]

# ---------------------------------------------------------------- templates
# The whole front end lives in this file on purpose: one module, no
# templates directory, no build step. Pages share BASE_HTML.

BASE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{% block title %}Automatic Photo Albums{% endblock %}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230f766e'/%3E%3Crect x='6' y='9' width='20' height='15' rx='2' fill='none' stroke='%23fff' stroke-width='2'/%3E%3Ccircle cx='12' cy='14' r='2' fill='%23fff'/%3E%3Cpath d='M8 22l5-5 4 4 3-3 4 4' fill='none' stroke='%23fff' stroke-width='2'/%3E%3C/svg%3E">
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1a16;--muted:#6b6459;--line:#e4dfd5;--soft:#e6f3f1;
  --accent:#0f766e;--accent-ink:#fff;--accent-hi:#0b5e58;--danger:#b4232c;--danger-bg:#fdecec;
  --ok:#2f855a;--radius:14px;--shadow:0 1px 2px rgba(0,0,0,.05),0 8px 24px -16px rgba(0,0,0,.25)}
@media (prefers-color-scheme:dark){:root{--bg:#121110;--card:#1b1917;--ink:#f1ede6;--muted:#a59d91;
  --line:#2e2a26;--soft:#17302d;--accent:#2dd4bf;--accent-ink:#06211f;--accent-hi:#5eead4;
  --danger:#fca5a5;--danger-bg:#3a1a1a;--ok:#6ee7a0;--shadow:0 1px 2px rgba(0,0,0,.4)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
a:hover{color:var(--accent-hi)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:6px}
h1,h2,h3{line-height:1.2;margin:0 0 .5rem;letter-spacing:-.01em}
h1{font-size:clamp(1.8rem,4vw,2.6rem)}
h2{font-size:1.4rem}
h3{font-size:1rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin-top:1.25rem}
p{margin:.4rem 0 .9rem}
.muted{color:var(--muted)}
.small{font-size:.9rem}
.lead{font-size:1.1rem;color:var(--muted);max-width:40rem}
.wrap{max-width:62rem;margin:0 auto;padding:1.5rem 1rem 3rem}
.top{display:flex;align-items:center;justify-content:space-between;gap:1rem;max-width:62rem;margin:0 auto;padding:.9rem 1rem;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:.6rem;color:var(--ink);text-decoration:none;font-weight:700}
.brand:hover{color:var(--accent)}
.logo{width:28px;height:28px;border-radius:7px;background:var(--accent);display:inline-grid;place-items:center;color:var(--accent-ink);font-size:14px}
.tag{font-size:.8rem;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:.15rem .6rem;white-space:nowrap}
footer{max-width:62rem;margin:0 auto;padding:1rem;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line)}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:1.25rem}
.btn{display:inline-flex;align-items:center;gap:.5rem;font:inherit;font-weight:600;font-size:1rem;padding:.7rem 1.3rem;border-radius:10px;
  border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);cursor:pointer;text-decoration:none;transition:transform .08s,background .15s}
.btn:hover{background:var(--accent-hi);border-color:var(--accent-hi);color:var(--accent-ink)}
.btn:active{transform:translateY(1px)}
.btn[disabled]{opacity:.45;cursor:not-allowed;transform:none}
.btn.ghost{background:transparent;color:var(--accent)}
.btn.ghost:hover{background:var(--soft)}
.pill{display:inline-block;font-size:.8rem;font-weight:600;border-radius:999px;padding:.15rem .65rem;background:var(--soft);color:var(--accent-hi);vertical-align:middle}
.error{background:var(--danger-bg);color:var(--danger);border:1px solid color-mix(in srgb,var(--danger) 35%,transparent);border-radius:10px;padding:.75rem 1rem}
/* home */
.hero{padding:2.5rem 0 1.5rem}
.drop{position:relative;display:block;border:2px dashed color-mix(in srgb,var(--accent) 55%,var(--line));border-radius:var(--radius);
  padding:2.5rem 1.5rem;text-align:center;background:var(--card);transition:border-color .15s,background .15s;cursor:pointer}
.drop:hover,.drop.over,.drop:focus-within{border-color:var(--accent);background:var(--soft)}
.drop.busy{pointer-events:none;opacity:.7}
.drop input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}
.drop .icon{width:52px;height:52px;margin:0 auto .75rem;border-radius:14px;background:var(--soft);color:var(--accent);display:grid;place-items:center}
.drop strong{font-size:1.15rem}
.drop .hint{display:block;color:var(--muted);margin-top:.35rem;font-size:.95rem}
.previews{list-style:none;margin:1rem 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:.5rem}
.previews li{position:relative;aspect-ratio:1;border-radius:10px;overflow:hidden;background:var(--line)}
.previews img,.previews .ph{width:100%;height:100%;object-fit:cover;display:grid;place-items:center;font-size:.75rem;font-weight:700;color:var(--muted)}
.previews .rm{position:absolute;top:4px;right:4px;width:24px;height:24px;border-radius:50%;border:0;background:rgba(0,0,0,.6);color:#fff;font-size:16px;line-height:1;cursor:pointer;opacity:0;transition:opacity .15s}
.previews li:hover .rm,.previews .rm:focus-visible{opacity:1}
.bar{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-top:1rem}
.count{font-weight:600}
.count.bad{color:var(--danger)}
.progress{position:relative;height:12px;border-radius:999px;background:var(--line);overflow:hidden;margin:1rem 0 .25rem}
.progress .fill{position:absolute;inset:0 auto 0 0;width:0;background:var(--accent);transition:width .2s}
.plabel{font-size:.9rem;color:var(--muted)}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem;margin:2.5rem 0 0;padding:0;list-style:none;counter-reset:step}
.steps li{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem;counter-increment:step}
.steps li::before{content:counter(step);display:inline-grid;place-items:center;width:1.6rem;height:1.6rem;border-radius:50%;background:var(--soft);color:var(--accent-hi);font-weight:700;font-size:.85rem;margin-bottom:.5rem}
.steps b{display:block;margin-bottom:.2rem}
.steps span{color:var(--muted);font-size:.92rem}
/* job */
.stages{list-style:none;margin:1.5rem 0;padding:0;display:grid;gap:.4rem}
.stages li{display:grid;grid-template-columns:1.75rem 1fr;gap:.75rem;align-items:start;padding:.65rem .9rem;border-radius:10px;color:var(--muted);transition:background .2s}
.stages li::before{content:"";width:1.4rem;height:1.4rem;border-radius:50%;border:2px solid var(--line);display:block;margin-top:.1rem}
.stages li.active{background:var(--card);color:var(--ink);font-weight:600;box-shadow:var(--shadow)}
.stages li.active::before{border-color:var(--accent);border-top-color:transparent;animation:spin .9s linear infinite}
.stages li.done{color:var(--ink)}
.stages li.done::before{background:var(--ok);border-color:var(--ok);content:"\\2713";color:#fff;display:grid;place-items:center;font-size:.8rem}
.stages .detail{display:block;font-weight:400;color:var(--muted);font-size:.9rem}
.status{display:flex;align-items:center;gap:.6rem;color:var(--muted)}
.spinner{width:1rem;height:1rem;border-radius:50%;border:2px solid var(--line);border-top-color:var(--accent);animation:spin .9s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spinner,.stages li.active::before{animation:none}}
/* results */
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.75rem;margin:1.25rem 0}
.summary .card{padding:.9rem 1rem}
.summary .num{font-size:1.8rem;font-weight:700;letter-spacing:-.02em;display:block}
.summary .lbl{color:var(--muted);font-size:.9rem}
.jump{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem;padding:0;list-style:none}
.jump a{display:inline-flex;align-items:center;gap:.4rem;text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:.3rem .8rem;color:var(--ink);background:var(--card);font-size:.9rem}
.jump a:hover{border-color:var(--accent)}
.collection{margin:1.5rem 0;padding:0;overflow:hidden}
.col-head{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;padding:1.1rem 1.25rem .5rem}
.col-head h2{margin:0}
.swatches{display:inline-flex;gap:.3rem;margin-left:auto}
.swatch{display:inline-block;width:1.25rem;height:1.25rem;border-radius:6px;border:1px solid rgba(0,0,0,.15)}
.col-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:1.25rem;padding:.5rem 1.25rem 1.25rem}
@media (max-width:760px){.col-grid{grid-template-columns:1fr}}
.cover{margin:0}
.cover img{width:100%;border-radius:10px;display:block;border:1px solid var(--line)}
.cover figcaption{color:var(--muted);font-size:.85rem;margin-top:.4rem}
.meters{margin:0;display:grid;gap:.55rem}
.meters>div{display:grid;grid-template-columns:6.5rem 1fr 4rem;gap:.6rem;align-items:center;font-size:.92rem}
.meters dt{color:var(--muted)}
.meters dd{margin:0;display:contents}
.meters b{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.meter{position:relative;height:8px;border-radius:999px;background:var(--line);overflow:hidden}
.meter span{position:absolute;top:0;bottom:0;left:0;background:var(--accent);border-radius:999px}
.meter.center span{left:50%}
.meter.center span.neg{left:auto;right:50%;background:#4f86c6}
.meter.center::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:2px;background:var(--muted);opacity:.5}
.music{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:.9rem 1rem}
.music .track{margin:0 0 .2rem;font-size:1.05rem}
.music audio{width:100%;margin-top:.5rem}
details{margin-top:.6rem}
summary{cursor:pointer;color:var(--accent);font-size:.9rem;font-weight:600}
table.scores{width:100%;border-collapse:collapse;font-size:.88rem;margin-top:.5rem}
table.scores th,table.scores td{text-align:left;padding:.3rem .4rem;border-bottom:1px solid var(--line)}
table.scores td:last-child,table.scores th:last-child{text-align:right;font-variant-numeric:tabular-nums}
table.scores tr.win td{font-weight:700;color:var(--accent-hi)}
.profile{display:flex;flex-wrap:wrap;gap:.35rem .8rem;font-size:.85rem;color:var(--muted);margin:.4rem 0 0}
.video-wrap{border-top:1px solid var(--line);padding:1rem 1.25rem 1.25rem;background:var(--bg)}
.video-wrap video{width:100%;aspect-ratio:16/9;border-radius:10px;background:#000;display:block}
.actions{display:flex;gap:.6rem;flex-wrap:wrap;margin:.75rem 0 0}
.endcap{text-align:center;padding:2rem 0 0}
</style>
</head>
<body>
<header class="top">
  <a class="brand" href="{{ url_for('home') }}"><span class="logo" aria-hidden="true">&#9635;</span>Automatic Photo Albums</a>
  <span class="tag">SENG 691 &middot; Assignment 5</span>
</header>
<main class="wrap">
{% block body %}{% endblock %}
</main>
<footer>Photos are grouped with a pre-trained ResNet-50 and K-Means; music is matched by a fixed rule over each
collection's colors and detail. Nothing is chosen by hand.</footer>
{% block scripts %}{% endblock %}
</body>
</html>
"""

HOME = """{% extends "base.html" %}
{% block body %}
<section class="hero">
  <h1>Turn a pile of photos into albums.</h1>
  <p class="lead">Upload a set of photos. The system groups the ones that belong together, designs a cover for each
  collection, picks a music track to match its look, and renders a slideshow video you can download.</p>
</section>

<form id="form" action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
  <label class="drop" id="drop" for="photos">
    <input id="photos" type="file" name="photos" accept="image/*{% if heic %},.heic,.heif{% endif %}" multiple required>
    <span class="icon" aria-hidden="true">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
    </span>
    <strong>Drop photos here</strong> or click to choose
    <span class="hint">{{ min_photos }} to {{ max_photos }} photos. JPG, PNG, WebP{% if heic %} and HEIC{% endif %}.
    They stay on this server only as long as it takes to build your albums.</span>
  </label>
  <ul id="previews" class="previews" hidden aria-label="Selected photos"></ul>
  <div class="bar">
    <span id="count" class="count muted" aria-live="polite">No photos selected yet.</span>
    <button id="go" class="btn" type="submit">Make my albums</button>
  </div>
  <div id="progress" class="progress" hidden role="progressbar" aria-label="Upload progress"><div class="fill"></div></div>
  <p id="plabel" class="plabel" hidden></p>
  <p id="err" class="error" role="alert" hidden></p>
</form>

<ol class="steps" aria-label="How it works">
  <li><b>Look</b><span>A pre-trained ResNet-50 turns every photo into 2048 numbers that capture what is in it.</span></li>
  <li><b>Group</b><span>K-Means clusters those numbers; the number of collections is picked by silhouette score.</span></li>
  <li><b>Score</b><span>Brightness, saturation, warmth and detail become a music target. Creative Commons tracks from Jamendo are matched to it, with code-synthesized tracks as a fallback.</span></li>
  <li><b>Render</b><span>Each collection gets a cover sheet and a 720p slideshow with its track underneath.</span></li>
</ol>
{% endblock %}
{% block scripts %}
<script>
(function () {
  var input = document.getElementById('photos'), drop = document.getElementById('drop'),
      grid = document.getElementById('previews'), count = document.getElementById('count'),
      btn = document.getElementById('go'), form = document.getElementById('form'),
      prog = document.getElementById('progress'), fill = prog.querySelector('.fill'),
      plabel = document.getElementById('plabel'), err = document.getElementById('err');
  var MIN = {{ min_photos }}, MAX = {{ max_photos }};
  var files = [];

  function isImage(f) { return /^image\\//.test(f.type) || /\\.(heic|heif)$/i.test(f.name); }
  function same(a, b) { return a.name === b.name && a.size === b.size && a.lastModified === b.lastModified; }
  function add(list) {
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (!isImage(f) || files.some(function (g) { return same(f, g); })) continue;
      files.push(f);
    }
    render();
  }
  function tile(f, i) {
    var li = document.createElement('li');
    li.title = f.name;
    if (/^image\\//.test(f.type) && !/hei[cf]/i.test(f.type)) {
      var img = new Image();
      img.alt = '';
      img.src = URL.createObjectURL(f);
      img.onload = function () { URL.revokeObjectURL(img.src); };
      li.appendChild(img);
    } else {
      var ph = document.createElement('span');
      ph.className = 'ph';
      ph.textContent = (f.name.split('.').pop() || 'IMG').toUpperCase();
      li.appendChild(ph);
    }
    var rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'rm';
    rm.setAttribute('aria-label', 'Remove ' + f.name);
    rm.textContent = '\\u00d7';
    rm.onclick = function () { files.splice(i, 1); render(); };
    li.appendChild(rm);
    return li;
  }
  function render() {
    grid.innerHTML = '';
    grid.hidden = files.length === 0;
    files.forEach(function (f, i) { grid.appendChild(tile(f, i)); });
    var n = files.length, ok = n >= MIN && n <= MAX;
    var msg = n === 0 ? 'No photos selected yet.' : n + ' photo' + (n === 1 ? '' : 's') + ' selected.';
    if (n > 0 && n < MIN) msg += ' Add ' + (MIN - n) + ' more to continue.';
    if (n > MAX) msg += ' Remove ' + (n - MAX) + ' to continue.';
    count.textContent = msg;
    count.classList.toggle('bad', n > 0 && !ok);
    count.classList.toggle('muted', n === 0);
    btn.disabled = !ok;
    try {  // keep the real input in sync so a plain form submit also works
      var dt = new DataTransfer();
      files.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    } catch (e) { /* older browsers: the native file list is used as-is */ }
  }
  function fail(message) {
    err.textContent = message;
    err.hidden = false;
    prog.hidden = true; plabel.hidden = true; fill.style.width = '0';
    drop.classList.remove('busy');
    btn.disabled = false;
  }

  input.addEventListener('change', function () { add(input.files); });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
  });
  drop.addEventListener('drop', function (e) { add(e.dataTransfer.files); });

  form.addEventListener('submit', function (e) {
    if (!window.FormData || !window.XMLHttpRequest) return;  // plain submit still works
    e.preventDefault();
    var fd = new FormData();
    files.forEach(function (f) { fd.append('photos', f, f.name); });
    var xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      var p = Math.round(ev.loaded / ev.total * 100);
      fill.style.width = p + '%';
      prog.setAttribute('aria-valuenow', p);
      plabel.textContent = p < 100 ? 'Uploading ' + p + '%' : 'Upload complete. Starting the pipeline';
    };
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300 && xhr.responseURL) { window.location = xhr.responseURL; return; }
      var m = 'The upload was not accepted.';
      try { m = JSON.parse(xhr.responseText).error || m; } catch (_) {}
      fail(m);
    };
    xhr.onerror = function () { fail('The upload did not go through. Check your connection and try again.'); };
    err.hidden = true; prog.hidden = false; plabel.hidden = false; plabel.textContent = 'Uploading';
    btn.disabled = true; drop.classList.add('busy');
    xhr.send(fd);
  });
  render();
})();
</script>
{% endblock %}
"""

JOB_PAGE = """{% extends "base.html" %}
{% block title %}Making your albums{% endblock %}
{% block body %}
<h1>Making your albums</h1>
<p class="lead">This usually takes a minute or two, longer for big uploads. Keep this page open; it will move to
your albums when they are ready.</p>
<ol class="stages" id="stages" aria-label="Pipeline stages">
{% for key, name in stages %}
  <li data-key="{{ key }}"><span><span class="name">{{ name }}</span><span class="detail"></span></span></li>
{% endfor %}
</ol>
<p class="status" id="status"><span class="spinner" aria-hidden="true"></span>
  <span id="step" aria-live="polite">Starting</span><span class="small" id="elapsed"></span></p>
<div id="error" hidden>
  <p class="error"><strong>Something went wrong.</strong> <span id="errmsg"></span></p>
  <p><a class="btn" href="{{ url_for('home') }}">Try again with other photos</a></p>
</div>
{% endblock %}
{% block scripts %}
<script>
(function () {
  var stages = Array.prototype.slice.call(document.querySelectorAll('#stages li'));
  var stepEl = document.getElementById('step'), elapsedEl = document.getElementById('elapsed'),
      errBox = document.getElementById('error'), errMsg = document.getElementById('errmsg'),
      status = document.getElementById('status');
  var STATUS = {{ url_for('job_status', job_id=job_id)|tojson }};
  var RESULTS = {{ url_for('results', job_id=job_id)|tojson }};
  var t0 = Date.now(), failures = 0, timer;

  function tick() {
    var s = Math.floor((Date.now() - t0) / 1000);
    elapsedEl.textContent = ' (' + (s < 60 ? s + 's' : Math.floor(s / 60) + 'm ' + (s % 60) + 's') + ')';
  }
  function show(step) {
    var idx = -1;
    stages.forEach(function (li, i) { if (step.indexOf(li.getAttribute('data-key')) === 0) idx = i; });
    stepEl.textContent = idx === -1 ? step : 'Working on it';
    stages.forEach(function (li, i) {
      li.classList.toggle('done', idx > i);
      li.classList.toggle('active', idx === i);
      var name = li.querySelector('.name').textContent;
      li.querySelector('.detail').textContent = (idx === i && step !== name) ? step : '';
    });
  }
  function broken(message) {
    clearInterval(timer);
    errMsg.textContent = message;
    errBox.hidden = false;
    status.hidden = true;
    document.title = 'Something went wrong';
  }
  function poll() {
    fetch(STATUS, { cache: 'no-store' }).then(function (r) {
      if (r.status === 404) throw { fatal: true, message: 'This job is no longer on the server.' };
      return r.json();
    }).then(function (s) {
      failures = 0;
      if (s.state === 'done') {
        stages.forEach(function (li) { li.classList.add('done'); li.classList.remove('active'); });
        stepEl.textContent = 'Done. Opening your albums';
        window.location = RESULTS;
        return;
      }
      if (s.state === 'error') { broken(s.step); return; }
      show(s.step);
      setTimeout(poll, 2000);
    }).catch(function (e) {
      if (e && e.fatal) { broken(e.message); return; }
      if (++failures > 5) { broken('Lost contact with the server. Reload this page to keep waiting.'); return; }
      setTimeout(poll, 3000);
    });
  }
  timer = setInterval(tick, 1000);
  poll();
})();
</script>
{% endblock %}
"""

RESULTS = """{% extends "base.html" %}
{% block title %}Your albums{% endblock %}
{% block body %}
<h1>Your albums</h1>
<p class="lead">{{ result.n_images }} photos, grouped into {{ result.chosen_k }} collections without any labels or
hints. Each collection has a cover, a matched track, and a slideshow video.</p>
<div class="summary">
  <div class="card"><span class="num">{{ result.n_images }}</span><span class="lbl">photos</span></div>
  <div class="card"><span class="num">{{ result.chosen_k }}</span><span class="lbl">collections</span></div>
  {% if silhouette is not none %}
  <div class="card"><span class="num">{{ "%.2f"|format(silhouette) }}</span><span class="lbl">silhouette score</span></div>
  {% endif %}
  <div class="card"><span class="num">{{ result.clusters|map(attribute="size")|max }}</span><span class="lbl">photos in the largest</span></div>
</div>
<ul class="jump" aria-label="Jump to a collection">
{% for c in result.clusters %}
  <li><a href="#collection-{{ loop.index }}"><span class="swatch" style="background:{{ c.dominant_colors[0] if c.dominant_colors else '#999' }}"></span>Collection {{ loop.index }} <span class="muted">&middot; {{ c.size }}</span></a></li>
{% endfor %}
</ul>

{% for c in result.clusters %}
{% set music = c.music %}
{% set jamendo = music.source == "jamendo" %}
{% set n = loop.index %}
<article class="card collection" id="collection-{{ n }}">
  <header class="col-head">
    <h2>Collection {{ n }}</h2>
    <span class="pill">{{ c.size }} photo{{ "" if c.size == 1 else "s" }}</span>
    <span class="swatches" aria-label="Dominant colors">
      {% for col in c.dominant_colors %}<span class="swatch" style="background:{{ col }}" title="{{ col }}"></span>{% endfor %}
    </span>
  </header>
  <div class="col-grid">
    <figure class="cover">
      <img src="{{ url_for('files', job_id=job_id, rel='output/' ~ c.montage) }}"
           alt="Cover sheet for collection {{ n }}: the photos closest to its center" loading="lazy">
      <figcaption>Cover sheet, built from the photos nearest the collection's center.</figcaption>
    </figure>
    <div class="facts">
      <h3>The look</h3>
      <dl class="meters">
        <div><dt>Brightness</dt><dd><div class="meter"><span style="width:{{ (c.mean_brightness * 100)|round|int }}%"></span></div><b>{{ "%.2f"|format(c.mean_brightness) }}</b></dd></div>
        <div><dt>Saturation</dt><dd><div class="meter"><span style="width:{{ (c.mean_saturation * 100)|round|int }}%"></span></div><b>{{ "%.2f"|format(c.mean_saturation) }}</b></dd></div>
        <div><dt>Warmth</dt><dd><div class="meter center"><span class="{{ 'neg' if c.mean_warmth < 0 else 'pos' }}" style="width:{{ (c.mean_warmth|abs * 50)|round|int }}%"></span></div><b>{{ "%+.2f"|format(c.mean_warmth) }}</b></dd></div>
        <div><dt>Detail</dt><dd><div class="meter"><span style="width:{{ (c.mean_edge_density / max_detail * 100)|round|int }}%"></span></div><b>{{ "%.3f"|format(c.mean_edge_density) }}</b></dd></div>
      </dl>
      <h3>Music</h3>
      <div class="music">
        <p class="track"><strong>{{ music.track }}</strong>
          {% if jamendo %}<span class="pill">Creative Commons</span>{% else %}<span class="pill">Synthesized in code</span>{% endif %}</p>
        {% if jamendo %}
        <p class="muted small">by {{ music.artist }}, from <a href="{{ music.page_url }}" rel="noopener">Jamendo</a>{% if music.license_ccurl %}
          under <a href="{{ music.license_ccurl }}" rel="noopener license">this licence</a>{% endif %}.
          The rule searched for {{ music.query_tags|join(", ") }} music at {{ music.query_speed }} speed and kept the best-scoring track.</p>
        {% else %}
        <p class="muted small">Chosen by the rule: detail sets the tempo, brightness and saturation set the mode,
          register and timbre. Lowest weighted distance wins.</p>
        {% endif %}
        <audio controls preload="none" src="{{ url_for('files', job_id=job_id, rel='music/' ~ music.file) }}"></audio>
        {% if music.scores %}
        <details>
          <summary>How the rule scored the synthesized tracks</summary>
          {% if music.target %}
          <p class="profile">
            <span>Target</span>
            <span>tempo {{ "%.0f"|format(music.target.tempo_norm * 100) }}%</span>
            <span>major {{ "%.0f"|format(music.target.major * 100) }}%</span>
            <span>timbre {{ "%.0f"|format(music.target.timbre * 100) }}%</span>
            <span>register {{ "%.0f"|format(music.target.register_norm * 100) }}%</span>
            <span>warmth {{ "%.0f"|format(music.target.warmth * 100) }}%</span>
          </p>
          {% endif %}
          {% set winner = music.synth_track or music.track %}
          <table class="scores">
            <thead><tr><th>Track</th><th>Distance (lower is better)</th></tr></thead>
            <tbody>
            {% for name, score in music.scores|dictsort(by="value") %}
              <tr{% if name == winner %} class="win"{% endif %}><td>{{ name }}{% if name == winner %} &#10003;{% endif %}</td><td>{{ "%.3f"|format(score) }}</td></tr>
            {% endfor %}
            </tbody>
          </table>
          {% if jamendo %}<p class="muted small">The synthesized winner set the search target; the Jamendo track above replaced it.</p>{% endif %}
        </details>
        {% endif %}
      </div>
    </div>
  </div>
  <div class="video-wrap">
    <video controls preload="none" playsinline
           poster="{{ url_for('files', job_id=job_id, rel='output/' ~ c.montage) }}"
           src="{{ url_for('files', job_id=job_id, rel='output/' ~ c.video) }}"></video>
    <p class="actions">
      <a class="btn ghost" href="{{ url_for('files', job_id=job_id, rel='output/' ~ c.video) }}" download="album-{{ n }}.mp4">Download video</a>
      <a class="btn ghost" href="{{ url_for('files', job_id=job_id, rel='music/' ~ music.file) }}" download>Download track</a>
    </p>
  </div>
</article>
{% endfor %}
<p class="endcap"><a class="btn" href="{{ url_for('home') }}">Make another album</a></p>
{% endblock %}
"""

ERROR_PAGE = """{% extends "base.html" %}
{% block title %}{{ title }}{% endblock %}
{% block body %}
<h1>{{ title }}</h1>
<p class="lead">{{ message }}</p>
<p><a class="btn" href="{{ url_for('home') }}">Back to the start</a></p>
{% endblock %}
"""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024
app.jinja_loader = DictLoader({
    "base.html": BASE_HTML, "home.html": HOME, "job.html": JOB_PAGE,
    "results.html": RESULTS, "error.html": ERROR_PAGE,
})


def _page_error(message, status, title="That did not work"):
    """Error as JSON for the page's uploader, as a page for everyone else."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(error=message), status
    return render_template("error.html", title=title, message=message), status


@app.errorhandler(404)
def _not_found(_exc):
    return _page_error("There is nothing at that address. Jobs are removed when the server restarts.",
                       404, "Not found")


@app.errorhandler(413)
def _too_large(_exc):
    return _page_error("That upload is too large. Try fewer or smaller photos.", 413)


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


def _save_photos(files, images_dir):
    """Re-encode every readable upload as JPEG; return how many were kept."""
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
    return saved


@app.route("/")
def home():
    return render_template("home.html", heic=HEIC_OK, min_photos=MIN_PHOTOS, max_photos=MAX_PHOTOS)


@app.route("/upload", methods=["POST"])
def upload():
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not (MIN_PHOTOS <= len(files) <= MAX_PHOTOS):
        return _page_error(f"Please upload between {MIN_PHOTOS} and {MAX_PHOTOS} photos.", 400)
    job_id = uuid.uuid4().hex[:12]
    images_dir = JOBS / job_id / "images"
    images_dir.mkdir(parents=True)
    if _save_photos(files, images_dir) < MIN_PHOTOS:
        return _page_error(f"Fewer than {MIN_PHOTOS} of those files could be read as photos.", 400)
    JOBS_STATE[job_id] = {"state": "working", "step": "Starting"}
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return redirect(url_for("job_page", job_id=job_id))


@app.route("/job/<job_id>")
def job_page(job_id):
    if job_id not in JOBS_STATE and not (JOBS / job_id).exists():
        abort(404)
    return render_template("job.html", job_id=job_id, stages=STAGES)


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
    clusters = result["clusters"]
    max_detail = max([c["mean_edge_density"] for c in clusters] + [1e-9])
    silhouette = result.get("silhouette_by_k", {}).get(str(result["chosen_k"]))
    return render_template("results.html", result=result, job_id=job_id,
                           max_detail=max_detail, silhouette=silhouette)


@app.route("/files/<job_id>/<path:rel>")
def files(job_id, rel):
    return send_from_directory(JOBS / job_id, rel)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
