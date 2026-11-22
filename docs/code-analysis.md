# Code analysis: CLOC and Lizard

Measured on November 21, 2026, over the application source (`app.py`,
`pipeline.py`, `music.py`, `jamendo.py`, `beats.py`) and the test suite
(`tests/`). Full tool outputs are in `cloc.txt`, `lizard.txt`, and
`pytest.txt` in this folder.

## CLOC (cloc 2.06)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Python | 11 | 257 | 611 | 1057 |

The comment count is inflated by the page templates embedded in
`app.py`: CSS rules whose selectors begin with `#` are counted as
Python comments by cloc. The code count is unaffected.

## Lizard (cyclomatic complexity)

The five application modules total 1,323 non-comment lines across 51
functions, with an average cyclomatic complexity of 3.7. Most of
`app.py`'s 732 lines are its embedded page templates.

One warning: `run_pipeline` in `pipeline.py` has a cyclomatic complexity
of 22 (threshold 15) at 87 NLOC. It is the orchestration function that
sequences statistics, embeddings, clustering, covers, music selection
(the Jamendo attempt and the synthesized fallback), beat analysis, and
one video build per cluster; its complexity is the accumulated branching
of those stages rather than nested logic. Splitting the per-cluster
cover and video stages into a helper would bring it under the threshold
and is the first refactoring candidate.

## Tests

40 unit tests, all passing (pytest 9.0.3, about eight seconds).
Coverage by area: music synthesis and the selection rule (6), visual
statistics, k selection, and montage geometry (6), the Flask routes (16:
the home, job, results and error pages, upload validation as a page and
as JSON, the redirect from results to the job page, the example-run
route and its photo fetcher, and the backdrop with its credits and
files), the Jamendo query mapping, candidate scoring, and fallbacks (7),
and beat detection against synthetic tracks at known tempos plus the
segment planner's grid invariants (5).
