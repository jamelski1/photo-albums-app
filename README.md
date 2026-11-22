# Automatic Photo Albums (web version)

A small web app built from the SENG 691 Assignment 5 system. A visitor
uploads a set of photos and the app:

1. Measures visual statistics for every photo (brightness, saturation,
   warm/cool balance, edge density, dominant colors).
2. Extracts ResNet-50 embeddings (pre-trained on ImageNet, classification
   head removed) and L2-normalizes them.
3. Groups the photos with K-Means, choosing the number of collections by
   silhouette score.
4. Builds a contact-sheet cover for each collection from the photos
   closest to its center.
5. Picks background music per collection with a fixed rule over the
   collection's visual statistics. The rule first produces a target
   profile (edge density drives tempo; brightness and saturation drive
   mode, register and timbre; warmth carries over). With a Jamendo API
   client ID configured, the target becomes a mood-tag and tempo search
   over Jamendo's Creative Commons catalog and the best-scoring real
   track is downloaded, with its artist and licence credited on the
   results page. Without an ID, or if the API is unreachable, the app
   falls back to a small library of original tracks synthesized in code,
   scored by weighted distance to the same target. Either way the choice
   is algorithmic, never manual and never random, and the scores are
   kept in the job's result file.
6. Generates a slideshow video per collection on a blurred-fill 1280x720
   canvas, with each photo shown for a whole number of beats of the
   chosen track and the fades landing on the beat (fixed 2.6-second
   timing when no beat can be measured), and the track mixed in.

## Links

- Live service: https://photo-albums-y7ir.onrender.com
- Jupyter notebook with the full 240-image run (opens in Google Colab):
  https://colab.research.google.com/github/jamelski1/seng691-hw5/blob/main/seng691-hw5.ipynb
- A generated slideshow video (Google Drive):
  https://drive.google.com/file/d/1i85gaqTzuXiqpCSvA3wFZmRBnSUAeHzE/view
- Assignment repository (notebook, report, dataset manifest):
  https://github.com/jamelski1/seng691-hw5
- Dataset (public): the manifest of all 240 seed photographs, with
  creators, licenses, and Wikimedia Commons source pages:
  https://github.com/jamelski1/photo-albums-app/blob/main/data/example_manifest.csv

## Run locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

Open http://localhost:5000 and upload between 8 and 240 photos, or run the built-in example over the 240-photo seed set from the assignment run.

For real music instead of the synthesized fallback, register a free
non-commercial app at https://devportal.jamendo.com and set the client
ID in the environment before starting:

```bash
JAMENDO_CLIENT_ID=your_client_id ./venv/bin/python app.py
```

## Deploy on Render

The included `render.yaml` defines the service. Connect this repository
in the Render dashboard (New, then Web Service) and it will use the file.

Memory note: the ResNet-50 step needs more memory than Render's free and
starter tiers provide, so the service is set to the Standard plan (2 GB).
On a smaller plan the feature step runs out of memory.

## Layout

- `app.py` — Flask app: upload, background job, status polling, results.
  The three pages (drag-and-drop uploader with previews and upload
  progress, a staged progress page, and the results page with covers,
  statistics, music attribution and videos) are inline templates in this
  file, so there is no templates directory and no front-end build.
- `static/backdrop/` — five photographs that drift and crossfade behind
  the home and progress pages: Ansel Adams' National Park Service series
  (1933 to 1942) from the U.S. National Archives, public domain, via
  Wikimedia Commons. The source page of each one is linked in the page
  footer and listed in `BACKDROP` in `app.py`.
- `pipeline.py` — statistics, embeddings, clustering, covers, videos.
- `music.py` — procedural track synthesis and the selection rule, carried
  over from the assignment system.
- `jamendo.py` — Jamendo API source: target-to-query mapping, candidate
  scoring, download, and attribution data.
- `tests/` — unit tests (28, all passing).
- `docs/` — CLOC and Lizard code analysis with full tool outputs.
- `jobs/` — one folder per upload (created at runtime, not committed).
