# Code analysis: CLOC and Lizard

Measured on November 21, 2026, over the application source (`app.py`,
`pipeline.py`, `music.py`, `jamendo.py`) and the test suite (`tests/`).
Full tool outputs are in `cloc.txt`, `lizard.txt`, and `pytest.txt` in
this folder.

## CLOC (cloc 2.06)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Python | 9 | 178 | 149 | 724 |

## Lizard (cyclomatic complexity)

The four application modules total 605 non-comment lines across 34
functions, with an average cyclomatic complexity of 3.8.

One warning: `run_pipeline` in `pipeline.py` has a cyclomatic complexity
of 21 (threshold 15) at 81 NLOC. It is the orchestration function that
sequences statistics, embeddings, clustering, covers, music selection
(now with the Jamendo attempt and the synthesized fallback), and one
video build per cluster; its complexity is the accumulated branching of
those stages rather than nested logic. Splitting the per-cluster cover
and video stages into a helper would bring it under the threshold and
is the first refactoring candidate.

## Tests

23 unit tests, all passing (pytest 9.2.0, about 6 seconds). Coverage by
area: music synthesis and the selection rule (6), visual statistics,
k selection, and montage geometry (6), the Flask routes (4), and the
Jamendo query mapping, candidate scoring, and fallbacks (7).
