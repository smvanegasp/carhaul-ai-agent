# Noisy-call runs

Scripted calls to Mia with background noise mixed into the caller's microphone (classroom
chatter, subway, cafe) at two levels, against each noise-handling profile: `baseline` (none,
how Mia was), `filter` (background voice cancellation only) and `full` (filter + turn limit +
noisy-call mode; see [`agent/src/mia/noise.py`](../../src/mia/noise.py)). Run them after
changes to how Mia listens: `uv run python -m evals.noisy_calls --label <name>` (in `agent/`,
with a local worker running). How it works: [`agent/evals/noisy_calls.py`](../noisy_calls.py).

Newest first ("Lines answered" counts noisy calls only):

| Run (UTC) | Label | Calls | Lines answered | |
| --- | --- | ---: | --- | --- |
| 2026-11-12T23:06:23+00:00 | first-grid | 21 | baseline 5/18, filter 12/18, full 16/18 | [report](runs/20261112T2250Z_first-grid/report.md) |
