# Code analysis: CLOC and Lizard

Measured on November 21, 2026, over the application source (`app.py`,
`pipeline.py`, `music.py`) and the test suite (`tests/`). Full tool
outputs are in `cloc.txt`, `lizard.txt`, and `pytest.txt` in this folder.

## CLOC (cloc 2.06)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Python | 7 | 135 | 114 | 554 |

The three application modules carry 483 non-comment lines by Lizard's
count; the rest of the CLOC total is the test suite.

## Lizard (cyclomatic complexity)

| File | NLOC | Functions | Avg NLOC | Avg CCN |
|---|---|---|---|---|
| app.py | 144 | 8 | 6.8 | 2.6 |
| pipeline.py | 194 | 9 | 20.6 | 4.7 |
| music.py | 145 | 9 | 11.6 | 2.8 |
| **Total** | **483** | **26** | **13.2** | **3.4** |

One warning: `run_pipeline` in `pipeline.py` has a cyclomatic complexity
of 19 (threshold 15) at 71 NLOC. It is the orchestration function that
sequences statistics, embeddings, clustering, covers, music selection,
and one video build per cluster; its complexity is the accumulated
branching of those stages rather than nested logic. Splitting the
per-cluster cover and video stages into a helper would bring it under
the threshold and is the first refactoring candidate.

## Tests

16 unit tests, all passing (pytest 9.2.0, about 5 seconds). Coverage by
area: music synthesis and the selection rule (6), visual statistics,
k selection, and montage geometry (6), and the Flask routes (4).
