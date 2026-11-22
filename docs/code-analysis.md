# Code analysis: CLOC and Lizard

Measured on November 21, 2026, over the application source (`app.py`,
`pipeline.py`, `music.py`, `jamendo.py`) and the test suite (`tests/`).
Full tool outputs are in `cloc.txt`, `lizard.txt`, and `pytest.txt` in
this folder.

## CLOC (cloc 2.06)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Python | 9 | 178 | 149 | 724 |

The CLOC table was measured before the interface refresh of `app.py`,
which added about 432 lines, nearly all of them the inline HTML,
CSS and JavaScript of the three pages (the app keeps its templates in the
module on purpose: one file, no build step).

## Lizard (cyclomatic complexity)

The four application modules total 1042 non-comment lines across 38
functions, with an average cyclomatic complexity of 3.5. Lizard counts
the lines of the page templates in `app.py` as code, which is where most
of the total comes from; the twelve functions in `app.py` average a
complexity of 2.2 and none exceeds 4.

One warning: `run_pipeline` in `pipeline.py` has a cyclomatic complexity
of 21 (threshold 15) at 81 NLOC. It is the orchestration function that
sequences statistics, embeddings, clustering, covers, music selection
(now with the Jamendo attempt and the synthesized fallback), and one
video build per cluster; its complexity is the accumulated branching of
those stages rather than nested logic. Splitting the per-cluster cover
and video stages into a helper would bring it under the threshold and
is the first refactoring candidate.

## Tests

32 unit tests, all passing (pytest 9.0.3, about 7 seconds). Coverage by
area: music synthesis and the selection rule (6), visual statistics,
k selection, and montage geometry (6), the Flask routes (13: the home,
job, results and error pages, upload validation as a page and as JSON,
the redirect from results to the job page, and the backdrop with its
credits and files), and the Jamendo query mapping, candidate scoring,
and fallbacks (7).
