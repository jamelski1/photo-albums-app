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
5. Synthesizes a small library of original music tracks in code and picks
   one per collection with a fixed weighted-distance rule over the
   collection's visual statistics (edge density drives tempo; brightness
   and saturation drive mode, register and timbre; warmth carries over).
   The choice is algorithmic, never manual and never random, and the
   scores are kept in the job's result file.
6. Generates a slideshow video per collection (2.6 seconds per photo on a
   blurred-fill 1280x720 canvas with fades) with the chosen track mixed in.

## Run locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

Open http://localhost:5000 and upload between 8 and 60 photos.

## Deploy on Render

The included `render.yaml` defines the service. Connect this repository
in the Render dashboard (New, then Web Service) and it will use the file.

Memory note: the ResNet-50 step needs more memory than Render's free and
starter tiers provide, so the service is set to the Standard plan (2 GB).
On a smaller plan the feature step runs out of memory.

## Layout

- `app.py` — Flask app: upload, background job, status polling, results.
- `pipeline.py` — statistics, embeddings, clustering, covers, videos.
- `music.py` — procedural track synthesis and the selection rule, carried
  over from the assignment system.
- `jobs/` — one folder per upload (created at runtime, not committed).
